import asyncio
import threading
import os

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

from coordinator.tools import delegate
from coordinator.registry import discover_agents

Langfuse()
langfuse_handler = CallbackHandler()

MCP_URL = os.getenv("ORDERS_MCP_URL", "http://orders-mcp:8004/mcp")

# Tools que o coordenador pode acessar via MCP — só leitura.
# Toda escrita (refund, voucher, incident) é responsabilidade dos especialistas.
COORDINATOR_ALLOWED_TOOLS = {"fetch_order"}

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
5. Consolide os resultados em uma resposta empática, clara e humanizada ao cliente

REGRA DE ESCALAÇÃO (decisão sua, não dos agentes):
- Após receber resposta do logistics-agent, verifique o campo `delay_days` (ou
  equivalente) na resposta.
- Se `delay_days > 3`: acione TAMBÉM o financial-agent passando apenas
  `order_id` e `return_reason="atraso_entrega"`. O financial-agent buscará
  o restante dos dados sozinho.
- Os agentes especialistas NÃO conhecem essa regra — é sua responsabilidade
  aplicá-la.

CONTRATO DE DELEGAÇÃO:
- Para logistics-agent: passe order_id e qualquer contexto pedido pelo agente.
- Para financial-agent: passe APENAS `order_id` e `return_reason`. Não envie
  valores monetários, datas ou método de pagamento — o agente busca isso por
  conta própria via suas tools."""


# ── Registry: carregado na importação do módulo pelo LangGraph Server ─────────
# Usa thread dedicada para evitar conflito com event loops do servidor.
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
        print("=== Agent Registry loaded ===")
        print(loaded)
    else:
        print("WARNING: Agent Registry empty — sub-agents may be unreachable at startup")
    return loaded


_registry_prompt = _load_registry()


# ── MCP tools: carregadas em thread dedicada para evitar conflito de event loop ─
def _load_mcp_tools() -> list:
    result: dict = {}

    async def _load():
        client = MultiServerMCPClient({
            "orders": {
                "transport": "streamable_http",
                "url": MCP_URL,
            }
        })
        all_tools = await client.get_tools()
        return [t for t in all_tools if t.name in COORDINATOR_ALLOWED_TOOLS]

    def _run():
        try:
            result["tools"] = asyncio.run(_load())
        except Exception as e:
            print(f"WARNING: Failed to load MCP tools from {MCP_URL}: {e}")
            result["tools"] = []

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)
    tools = result.get("tools", [])
    print(f"=== MCP tools loaded ({len(tools)}): {[t.name for t in tools]} ===")
    return tools


_mcp_tools = _load_mcp_tools()


# ── Prompt dinâmico: injeta o registry em cada invocação ─────────────────────
def get_prompt(state) -> list:
    return [SystemMessage(content=_INSTRUCTIONS_TEMPLATE.format(registry=_registry_prompt))]


# ── LangGraph ReAct Agent ─────────────────────────────────────────────────────
model = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)

graph = create_agent(
    model=model,
    tools=_mcp_tools + [delegate],
    system_prompt=get_prompt(None)[0],
).with_config({
    "callbacks": [langfuse_handler],
    "metadata": {"langfuse_tags": ["coordinator", "postvenda-ai"]},
})
