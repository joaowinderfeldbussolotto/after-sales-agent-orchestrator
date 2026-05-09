import asyncio
import threading
import os

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from coordinator.tools import fetch_order, fetch_refund_eligibility, delegate
from coordinator.registry import discover_agents

_INSTRUCTIONS_TEMPLATE = """Você é o Coordenador de Pós-Venda de um e-commerce brasileiro.

MISSÃO: Atender clientes com demandas pós-venda, buscar informações dos pedidos
e acionar os agentes especializados corretos via protocolo A2A.

CAPACIDADES PRÓPRIAS:
- Consultar dados completos de pedidos (fetch_order)
- Verificar elegibilidade de reembolso (fetch_refund_eligibility)
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


# ── Prompt dinâmico: injeta o registry em cada invocação ─────────────────────
def get_prompt(state) -> list:
    return [SystemMessage(content=_INSTRUCTIONS_TEMPLATE.format(registry=_registry_prompt))]


# ── LangGraph ReAct Agent ─────────────────────────────────────────────────────
model = ChatGroq(
    model="openai/gpt-oss-120b",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)

graph = create_react_agent(
    model=model,
    tools=[fetch_order, fetch_refund_eligibility, delegate],
    prompt=get_prompt,
    checkpointer=MemorySaver(),
)
