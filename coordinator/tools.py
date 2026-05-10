import asyncio
import httpx
from langchain_core.tools import tool

ORDERS_API = "http://mock-api:8003"


@tool
async def fetch_order(order_id: str) -> dict:
    """Busca dados completos de um pedido pelo ID no sistema do e-commerce.

    Args:
        order_id: ID do pedido (ex: PV-2026-00142)
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{ORDERS_API}/orders/{order_id}")
        if r.status_code == 404:
            return {"error": f"Pedido {order_id} não encontrado"}
        r.raise_for_status()
        return r.json()


@tool
async def fetch_refund_eligibility(order_id: str) -> dict:
    """Verifica se um pedido está elegível para reembolso ou devolução.

    Args:
        order_id: ID do pedido
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(f"{ORDERS_API}/orders/{order_id}/refund-eligibility")
        if r.status_code == 404:
            return {"error": f"Pedido {order_id} não encontrado"}
        r.raise_for_status()
        return r.json()


@tool
async def delegate(agent_name: str, task: str) -> str:
    """Delega uma tarefa para um agente especializado via protocolo A2A.

    Consulte os critérios ACIONAR QUANDO de cada agente no registro para
    decidir qual chamar. O nome do agente é exatamente como aparece no registro.

    Args:
        agent_name: Nome do agente conforme listado no registro de agentes
        task: Descrição completa da tarefa com todo o contexto necessário
              conforme CONTEXTO NECESSÁRIO especificado pelo agente escolhido
    """
    from coordinator.registry import AGENT_REGISTRY

    agent_info = AGENT_REGISTRY.get(agent_name)
    if not agent_info:
        return (
            f"Agente '{agent_name}' não encontrado no registro. "
            f"Agentes disponíveis: {list(AGENT_REGISTRY.keys())}"
        )

    base_url = agent_info["base_url"]
    protocol = agent_info.get("protocol", "json-rpc")
    message = {
        "kind": "message",
        "role": "user",
        "messageId": f"msg-{id(task)}",
        "parts": [{"kind": "text", "text": task}],
    }

    if protocol == "agno-rest":
        # Agno AgentOS REST A2A: POST directly, Task object returned without JSON-RPC wrapper
        endpoint = f"{base_url}/a2a/agents/{agent_name}/v1/message:send"
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                r = await client.post(endpoint, json={"message": message})
                task_result = r.json()
            except httpx.TimeoutException:
                return f"Timeout ao aguardar resposta de {agent_name}."
            except Exception as e:
                return f"Erro de comunicação com {agent_name}: {str(e)}"

        state = task_result.get("status", {}).get("state")
        if state == "completed":
            return _extract_artifact_text(task_result)
        task_id = task_result.get("id")
        if task_id and state in ("submitted", "working"):
            return await _poll_task_rest(base_url, agent_name, task_id, timeout=110)
        return f"Resposta inesperada de {agent_name}: {task_result}"

    # JSON-RPC (FastA2A / PydanticAI)
    payload = {
        "jsonrpc": "2.0",
        "id": "delegate-1",
        "method": "message/send",
        "params": {"message": message},
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            r = await client.post(f"{base_url}/", json=payload)
            response = r.json()
        except httpx.TimeoutException:
            return f"Timeout ao aguardar resposta de {agent_name}."
        except Exception as e:
            return f"Erro de comunicação com {agent_name}: {str(e)}"

    error = response.get("error")
    if error:
        return f"Erro do agente {agent_name}: {error.get('message', str(error))}"

    result = response.get("result", {})
    status_state = result.get("status", {}).get("state")

    if status_state == "completed":
        return _extract_artifact_text(result)

    # FastA2A (PydanticAI) — retorna 'working', faz polling
    task_id = result.get("id")
    if task_id and status_state in ("submitted", "working"):
        return await _poll_task(base_url, task_id, timeout=55)

    return f"Resposta inesperada de {agent_name}: {response}"


async def _poll_task(base_url: str, task_id: str, timeout: int = 55) -> str:
    """Poll a JSON-RPC A2A task until completed, failed, or timeout."""
    elapsed = 0.0
    interval = 1.5

    async with httpx.AsyncClient(timeout=10.0) as client:
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
            try:
                r = await client.post(
                    f"{base_url}/",
                    json={
                        "jsonrpc": "2.0",
                        "id": "poll-1",
                        "method": "tasks/get",
                        "params": {"id": task_id},
                    },
                )
                task = r.json().get("result", {})
            except Exception:
                continue

            state = task.get("status", {}).get("state")
            if state == "completed":
                return _extract_artifact_text(task)
            elif state in ("failed", "canceled"):
                return f"Task {task_id} encerrada com status: {state}"

    return f"Timeout após {timeout}s aguardando resposta da task {task_id}."


async def _poll_task_rest(base_url: str, agent_name: str, task_id: str, timeout: int = 110) -> str:
    """Poll an Agno REST A2A task until completed, failed, or timeout."""
    elapsed = 0.0
    interval = 1.5
    endpoint = f"{base_url}/a2a/agents/{agent_name}/v1/tasks/{task_id}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        while elapsed < timeout:
            await asyncio.sleep(interval)
            elapsed += interval
            try:
                r = await client.get(endpoint)
                task = r.json()
            except Exception:
                continue

            state = task.get("status", {}).get("state")
            if state == "completed":
                return _extract_artifact_text(task)
            elif state in ("failed", "canceled"):
                return f"Task {task_id} encerrada com status: {state}"

    return f"Timeout após {timeout}s aguardando resposta da task {task_id}."


def _extract_artifact_text(task: dict) -> str:
    """Extract text from the first artifact of an A2A task result."""
    artifacts = task.get("artifacts", [])
    if not artifacts:
        return "Agente não retornou resultado."
    parts = artifacts[0].get("parts", [])
    for part in parts:
        if part.get("kind") == "text" and part.get("text"):
            return part["text"]
    return str(parts[0]) if parts else "Artifact sem conteúdo."
