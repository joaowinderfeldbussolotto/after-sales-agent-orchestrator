import logging
import os

import httpx
from langchain_core.tools import tool
from langfuse import observe

logger = logging.getLogger(__name__)

_A2A_TIMEOUT = float(os.getenv("A2A_TIMEOUT", "60"))
_A2A_AGNO_TIMEOUT = float(os.getenv("A2A_AGNO_TIMEOUT", "120"))
_A2A_POLL_TIMEOUT = int(os.getenv("A2A_POLL_TIMEOUT", "55"))
_POLL_MAX_CONSECUTIVE_ERRORS = 3


def _client(timeout: float) -> httpx.AsyncClient:
    """httpx client com retry em falhas de conexão transientes."""
    transport = httpx.AsyncHTTPTransport(retries=3)
    return httpx.AsyncClient(timeout=timeout, transport=transport)


@observe(as_type="tool", name="a2a_agno_rest")
async def _call_agno_rest(endpoint: str, payload: dict, agent_name: str) -> str:
    """Span Langfuse: chamada A2A REST ao Agno."""
    async with _client(_A2A_AGNO_TIMEOUT) as client:
        r = await client.post(endpoint, json=payload)
        return _extract_agno_text(r.json())


@observe(as_type="tool", name="a2a_json_rpc_send")
async def _call_json_rpc(base_url: str, payload: dict) -> dict:
    """Span Langfuse: chamada message/send JSON-RPC."""
    async with _client(_A2A_TIMEOUT) as client:
        r = await client.post(f"{base_url}/", json=payload)
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
        endpoint = f"{base_url}/a2a/agents/{agent_name}/v1/message:send"
        payload = {
            "jsonrpc": "2.0",
            "id": f"req-{id(task)}",
            "params": {"message": message},
        }
        try:
            logger.info("A2A agno-rest → %s", endpoint)
            result = await _call_agno_rest(endpoint, payload, agent_name)
            logger.info("A2A agno-rest ← %s: %.120s", agent_name, result)
            return result
        except httpx.TimeoutException:
            logger.warning("A2A timeout: %s", agent_name)
            return f"Timeout ao aguardar resposta de {agent_name}."
        except Exception as e:
            logger.error("A2A error: %s — %s", agent_name, e)
            return f"Erro de comunicação com {agent_name}: {str(e)}"

    # JSON-RPC (FastA2A / PydanticAI)
    payload = {
        "jsonrpc": "2.0",
        "id": "delegate-1",
        "method": "message/send",
        "params": {"message": message},
    }

    try:
        logger.info("A2A json-rpc → %s/", base_url)
        response = await _call_json_rpc(base_url, payload)
    except httpx.TimeoutException:
        logger.warning("A2A timeout: %s", agent_name)
        return f"Timeout ao aguardar resposta de {agent_name}."
    except Exception as e:
        logger.error("A2A error: %s — %s", agent_name, e)
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
        return await _poll_task(base_url, task_id, timeout=_A2A_POLL_TIMEOUT)

    return f"Resposta inesperada de {agent_name}: {response}"


async def _poll_task(base_url: str, task_id: str, timeout: int = 55) -> str:
    """Poll a JSON-RPC A2A task until completed, failed, or timeout."""
    import asyncio

    elapsed = 0.0
    interval = 1.5
    consecutive_errors = 0

    async with _client(10.0) as client:
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
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logger.warning(
                    "poll error %d/%d for %s: %s",
                    consecutive_errors,
                    _POLL_MAX_CONSECUTIVE_ERRORS,
                    task_id,
                    e,
                )
                if consecutive_errors >= _POLL_MAX_CONSECUTIVE_ERRORS:
                    return f"Agente inacessível após {consecutive_errors} tentativas: {e}"
                continue

            state = task.get("status", {}).get("state")
            if state == "completed":
                return _extract_artifact_text(task)
            elif state in ("failed", "canceled"):
                return f"Task {task_id} encerrada com status: {state}"

    return f"Timeout após {timeout}s aguardando resposta da task {task_id}."


def _extract_artifact_text(task: dict) -> str:
    """Extract text from the first artifact of an A2A (JSON-RPC) task result."""
    artifacts = task.get("artifacts", [])
    if not artifacts:
        return "Agente não retornou resultado."
    parts = artifacts[0].get("parts", [])
    for part in parts:
        if part.get("kind") == "text" and part.get("text"):
            return part["text"]
    return str(parts[0]) if parts else "Artifact sem conteúdo."


def _extract_agno_text(response: dict) -> str:
    """Extract text from an Agno A2A REST response.

    Agno wraps the Task inside {"id": ..., "result": {...}}.
    Text lives in result.artifacts[].parts[] or result.history[].parts[].
    """
    result = response.get("result", response)

    # artifacts have priority (structured output)
    for artifact in result.get("artifacts") or []:
        for part in artifact.get("parts", []):
            text = part.get("text") or (part.get("root") or {}).get("text")
            if text:
                return text

    # fall back to agent history message
    for msg in result.get("history", []):
        if msg.get("role") in ("agent", "model"):
            for part in msg.get("parts", []):
                text = part.get("text") or (part.get("root") or {}).get("text")
                if text:
                    return text

    return "Agente não retornou resultado."
