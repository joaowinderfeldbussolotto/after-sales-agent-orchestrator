import os
from enum import Enum

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.agent import Agent as PydanticAgent
from langfuse import Langfuse

Langfuse()
PydanticAgent.instrument_all()

from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.toolsets import FilteredToolset

from . import tools


# ── Structured output ──────────────────────────────────────────────────────────

class DeliveryStatus(str, Enum):
    on_time = "on_time"
    delayed_minor = "delayed_minor"   # 1-3 dias
    delayed_major = "delayed_major"   # 4+ dias
    delivered = "delivered"


class LogisticsReport(BaseModel):
    status: DeliveryStatus
    delay_days: int
    incident_id: str | None = None
    tracking_events: list[str] = []
    message: str


# ── MCP toolset (escrita logística apenas) ─────────────────────────────────────

_LOGISTICS_MCP_TOOLS = {"open_incident", "update_order_status"}

_orders_mcp = FilteredToolset(
    MCPServerStreamableHTTP(
        os.getenv("ORDERS_MCP_URL", "http://orders-mcp:8004/mcp")
    ),
    lambda _ctx, tool_def: tool_def.name in _LOGISTICS_MCP_TOOLS,
)

_logistics_model = os.getenv("LOGISTICS_MODEL", "groq:meta-llama/llama-4-scout-17b-16e-instruct")

logistics_agent = Agent(
    _logistics_model,
    name="Logistics Agent",
    output_type=LogisticsReport,
    retries=3,
    instructions="""Você é o Agente de Logística de um e-commerce brasileiro.

RESPONSABILIDADES:
- Rastrear pedidos usando o código de rastreio
- Calcular atrasos de entrega
- Abrir ocorrências em transportadoras
- Cotar fretes reversos para devoluções
- Validar endereços de entrega

REGRAS:
1. Sempre use calculate_delay_days antes de qualquer outra ação
2. Se delayed=True e delay_days <= 3: status="delayed_minor"; se delay_days > 3: status="delayed_major"
3. Se delayed=True: abra uma ocorrência logística com open_incident e registre o incident_id
4. Se delayed=False: status="on_time", delay_days=0
5. Se já entregue: status="delivered", delay_days=0""",
    toolsets=[_orders_mcp],
    tools=[
        tools.track_package,
        tools.quote_reverse_shipping,
        tools.validate_address,
        tools.calculate_delay_days,
    ],
    instrument=True,
)


app = logistics_agent.to_a2a(
    name="logistics-agent",
    description="""Especialista em rastreamento de pedidos, ocorrências logísticas e frete reverso.

ACIONAR QUANDO:
- Cliente pergunta sobre rastreio, localização ou status da entrega
- Pedido com atraso ou prazo de entrega ultrapassado
- Solicitação de frete reverso ou coleta para devolução
- Abertura de ocorrência por extravio, avaria ou não entregue
- Validação ou problema com endereço de entrega

CONTEXTO NECESSÁRIO AO DELEGAR: order_id, tracking_code, expected_delivery, current_status""",
    version="1.0.0",
)
