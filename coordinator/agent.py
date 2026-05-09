from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agno.agent import Agent
from agno.models.groq import Groq
from agno.os.app import AgentOS
from agno.os.interfaces.agui import AGUI
from agno.db.sqlite import SqliteDb

from .tools import fetch_order, fetch_refund_eligibility, delegate
from .registry import discover_agents, AGENT_REGISTRY

# ── Startup: dynamic agent discovery ──────────────────────────────────────────
_registry_prompt: str = ""


async def _init_registry():
    global _registry_prompt
    _registry_prompt = await discover_agents()
    print("Agent Registry loaded:")
    print(_registry_prompt)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _init_registry()
    yield


# ── Agno Agent ────────────────────────────────────────────────────────────────
def build_coordinator() -> Agent:
    registry_snapshot = _registry_prompt

    return Agent(
        name="coordinator",
        model=Groq(id="openai/gpt-oss-120b"),
        db=SqliteDb(db_file="/data/coordinator.db"),
        instructions=f"""Você é o Coordenador de Pós-Venda de um e-commerce brasileiro.

MISSÃO: Interpretar a mensagem do cliente, buscar informações do pedido e acionar
os agentes especializados corretos via protocolo A2A.

{registry_snapshot}

FLUXO DE DECISÃO:
1. Extraia o order_id ou CPF da mensagem do cliente
2. Busque o pedido com fetch_order
3. Com base na intenção detectada, acione o agente correto via delegate:
   - Rastreio / Atraso → logistics-agent
   - Devolução / Reembolso → financial-agent
   - Atraso GRAVE (>3 dias): acione logistics-agent PRIMEIRO, depois financial-agent

REGRA DE ESCALAÇÃO:
- Se logistics-agent retornar escalate_financial=true OU delay_days > 3:
  acione TAMBÉM financial-agent com contexto completo

CONTEXTO PARA DELEGAÇÃO:
Ao usar delegate, inclua SEMPRE: order_id, tracking_code, order_date,
expected_delivery, items_total, freight_paid, payment_method e motivo do contato.

RESPOSTA FINAL:
Consolide os resultados dos agentes em uma resposta humanizada, empática e
clara para o cliente. Inclua: status do pedido, ação tomada, próximos passos
e prazo estimado.""",
        tools=[fetch_order, fetch_refund_eligibility, delegate],
        show_tool_calls=True,
        markdown=True,
        add_history_to_context=True,
        num_history_runs=5,
    )


# ── AgentOS + AGUI ────────────────────────────────────────────────────────────
coordinator_agent = build_coordinator()

agent_os = AgentOS(
    agents=[coordinator_agent],
    interfaces=[AGUI(agent=coordinator_agent)],
    lifespan=lifespan,
)

app = agent_os.get_app()

# CORS: allow Agent UI frontend (port 3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/status")
def status():
    return {"status": "ok", "registry": list(AGENT_REGISTRY.keys())}


# uvicorn coordinator.agent:app --host 0.0.0.0 --port 8000
