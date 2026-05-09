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

MISSÃO: Atender clientes com demandas pós-venda, buscar informações dos pedidos
e acionar os agentes especializados corretos via protocolo A2A.

CAPACIDADES PRÓPRIAS:
- Consultar dados completos de pedidos (fetch_order)
- Verificar elegibilidade de reembolso (fetch_refund_eligibility)
- Responder dúvidas simples que não requeiram especialista

{registry_snapshot}

PROCESSO DE ATENDIMENTO:
1. Identifique o order_id na mensagem do cliente
2. Busque os dados do pedido com fetch_order
3. Use os critérios ACIONAR QUANDO de cada agente acima para decidir qual acionar
4. Delegue via delegate incluindo o CONTEXTO NECESSÁRIO especificado por cada agente
5. Respeite as regras de ESCALAÇÃO definidas por cada agente
<<<<<<< HEAD
6. Consolide os resultados em uma resposta empática, clara e humanizada ao cliente""",
        tools=[fetch_order, fetch_refund_eligibility, delegate],
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/status")
def status():
    return {"status": "ok", "registry": list(AGENT_REGISTRY.keys())}


# uvicorn coordinator.agent:app --host 0.0.0.0 --port 8000
