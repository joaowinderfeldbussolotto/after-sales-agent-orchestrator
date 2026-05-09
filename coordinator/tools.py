import httpx
from agno.tools import tool

ORDERS_API = "http://mock-api:8003"


@tool("Buscar Pedido")
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


@tool("Verificar Elegibilidade de Reembolso")
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


@tool("Delegar para Agente Especializado")
async def delegate(agent_name: str, task: str) -> str:
    """Delega uma tarefa para um agente especializado via protocolo A2A.

    Consulte os critérios "Acionar quando" de cada agente no registro para
    decidir qual chamar. O nome do agente é exatamente como aparece no registro.

    Args:
        agent_name: Nome do agente conforme listado no registro de agentes
        task: Descrição completa da tarefa com todo o contexto necessário
              conforme "Contexto necessário ao delegar" do agente escolhido
    """
    from .registry import AGENT_REGISTRY

    agent_info = AGENT_REGISTRY.get(agent_name)
    if not agent_info:
        return (
            f"Agente '{agent_name}' não encontrado no registro. "
            f"Agentes disponíveis: {list(AGENT_REGISTRY.keys())}"
        )

    base_url = agent_info["base_url"]
    payload = {
        "jsonrpc": "2.0",
        "id": "delegate-1",
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": f"msg-{id(task)}",
                "parts": [{"kind": "text", "text": task}],
            }
        },
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
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
    state = result.get("status", {}).get("state")

    if state == "completed":
        return _extract_artifact_text(result)

    return f"Resposta inesperada de {agent_name}: estado={state}, resultado={result}"


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
