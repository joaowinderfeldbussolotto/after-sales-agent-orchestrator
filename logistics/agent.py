import os

from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStreamableHTTP
from pydantic_ai.toolsets import FilteredToolset

from . import tools

_LOGISTICS_MCP_TOOLS = {"open_incident", "update_order_status"}

_orders_mcp = FilteredToolset(
    MCPServerStreamableHTTP(
        os.getenv("ORDERS_MCP_URL", "http://orders-mcp:8004/mcp")
    ),
    lambda _ctx, tool_def: tool_def.name in _LOGISTICS_MCP_TOOLS,
)

logistics_agent = Agent(
    "groq:meta-llama/llama-4-scout-17b-16e-instruct",
    instructions="""Você é o Agente de Logística de um e-commerce brasileiro.

RESPONSABILIDADES:
- Rastrear pedidos usando o código de rastreio
- Calcular atrasos de entrega
- Abrir ocorrências em transportadoras
- Cotar fretes reversos para devoluções
- Validar endereços de entrega

REGRAS:
1. Sempre use calculate_delay_days antes de qualquer outra ação
2. Se delayed=True: abra uma ocorrência logística independente do número de dias
3. Se delayed=False: apenas informe o prazo atualizado
4. Retorne SEMPRE um JSON estruturado com: status, delay_days, incident_id (se aberto), message

FORMATO DE RESPOSTA:
{
  "status": "on_time|delayed_minor|delayed_major|delivered",
  "delay_days": 0,
  "incident_id": "ABC12345 ou null",
  "tracking_events": [...],
  "message": "Mensagem humanizada para o cliente"
}""",
    toolsets=[_orders_mcp],
    tools=[
        tools.track_package,
        tools.quote_reverse_shipping,
        tools.validate_address,
        tools.calculate_delay_days,
    ],
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
