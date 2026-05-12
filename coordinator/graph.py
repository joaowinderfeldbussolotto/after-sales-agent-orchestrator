import asyncio
import logging
import os
import threading

import httpx
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware, ToolRetryMiddleware
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from langchain_mcp_adapters.client import MultiServerMCPClient

from coordinator.tools import delegate
from coordinator.registry import discover_agents

logger = logging.getLogger(__name__)

Langfuse()
langfuse_handler = CallbackHandler()

_INSTRUCTIONS_TEMPLATE = """Você é o Coordenador de Pós-Venda de um e-commerce brasileiro.

MISSÃO: Atender clientes com demandas pós-venda, buscar informações dos pedidos
e acionar os agentes especializados corretos via protocolo A2A.

CAPACIDADES PRÓPRIAS:
- Consultar dados completos de pedidos (fetch_order)
- Responder dúvidas simples que não requeiram especialista

{registry}

PROCESSO DE ATENDIMENTO:
1. Identifique o order_id na mensagem do cliente
2. Busque os dados do pedido com fetch_order
3. Use os critérios ACIONAR QUANDO de cada agente acima para decidir qual acionar
4. Delegue via delegate incluindo o CONTEXTO NECESSÁRIO especificado por cada agente
5. Respeite as regras de ESCALAÇÃO definidas por cada agente
6. Consolide os resultados em uma resposta empática, clara e humanizada ao cliente"""

# ── Registry: carregado na importação do módulo pelo LangGraph Server ─────────
_registry_prompt: str = ""


def _load_registry() -> str:
    result: dict = {}

    def _run():
        result["prompt"] = asyncio.run(discover_agents())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)
    loaded = result.get("prompt", "")
    if loaded:
        logger.info("Agent Registry loaded:\n%s", loaded)
    else:
        logger.warning(
            "Agent Registry empty — sub-agents may be unreachable at startup. "
            "Check LOGISTICS_URL and FINANCIAL_URL."
        )
    return loaded


_registry_prompt = _load_registry()


# ── MCP Tools: fetch_order carregada do orders-mcp via langchain-mcp-adapters ─
_MCP_TOOL_NAMES = {"fetch_order"}


def _load_mcp_tools() -> list:
    result: dict = {}

    def _run():
        async def _async():
            client = MultiServerMCPClient({
                "orders": {
                    "transport": "http",
                    "url": os.getenv("ORDERS_MCP_URL", "http://orders-mcp:8004/mcp"),
                }
            })
            all_tools = await client.get_tools()
            result["tools"] = [t for t in all_tools if t.name in _MCP_TOOL_NAMES]

        asyncio.run(_async())

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)
    loaded = result.get("tools", [])
    if loaded:
        logger.info("MCP Tools loaded: %s", [t.name for t in loaded])
    else:
        logger.warning(
            "MCP Tools empty — orders-mcp may be unreachable at startup. "
            "Check ORDERS_MCP_URL. fetch_order will be unavailable."
        )
    return loaded


_mcp_tools = _load_mcp_tools()


# ── Prompt dinâmico: injeta o registry em cada invocação ─────────────────────
def get_prompt(state) -> list:
    return [SystemMessage(content=_INSTRUCTIONS_TEMPLATE.format(registry=_registry_prompt))]


# ── LangGraph ReAct Agent ─────────────────────────────────────────────────────
_coordinator_model = os.getenv("COORDINATOR_MODEL", "openai/gpt-oss-120b")

# Rate limiter: Groq free tier ≈ 30 req/min; 0.4 req/s = 24/min com margem
_rate_limiter = InMemoryRateLimiter(requests_per_second=0.4)

model = ChatGroq(
    model=_coordinator_model,
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
    rate_limiter=_rate_limiter,
)

graph = create_agent(
    model=model,
    tools=[*_mcp_tools, delegate],
    system_prompt=get_prompt(None)[0],
    middleware=[
        ModelRetryMiddleware(
            max_retries=2,
            retry_on=(httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException),
            backoff_factor=2.0,
            initial_delay=1.0,
            jitter=True,
            on_failure="continue",
        ),
        ToolRetryMiddleware(
            max_retries=2,
            tools=["fetch_order", "delegate"],
            retry_on=(httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException),
            backoff_factor=2.0,
            initial_delay=1.0,
            jitter=True,
            on_failure="return_message",
        ),
    ],
).with_config({
    "callbacks": [langfuse_handler],
    "metadata": {"langfuse_tags": ["coordinator", "postvenda-ai"]},
})
