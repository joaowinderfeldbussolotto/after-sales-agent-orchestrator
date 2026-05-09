from pydantic_ai import Agent
from . import tools

logistics_agent = Agent(
    "groq:llama-3.3-70b-versatile",
    instructions="""Você é o Agente de Logística de um e-commerce brasileiro.

RESPONSABILIDADES:
- Rastrear pedidos usando o código de rastreio
- Calcular atrasos de entrega
- Abrir ocorrências em transportadoras
- Cotar fretes reversos para devoluções
- Validar endereços de entrega

REGRAS:
1. Sempre use calculate_delay_days antes de qualquer outra ação
2. Se delayed=True e days > 3: abra uma ocorrência E sinalize no retorno que é necessário compensação financeira
3. Se delayed=True e days <= 3: abra a ocorrência mas NÃO sinalize escalação financeira
4. Se delayed=False: apenas informe o prazo atualizado
5. Retorne SEMPRE um JSON estruturado com: status, delay_info, incident_id (se aberto), escalate_financial, message

FORMATO DE RESPOSTA:
{
  "status": "on_time|delayed_minor|delayed_major|delivered",
  "delay_days": 0,
  "incident_id": "ABC12345 ou null",
  "escalate_financial": false,
  "tracking_events": [...],
  "message": "Mensagem humanizada para o cliente"
}""",
    tools=[
        tools.track_package,
        tools.quote_reverse_shipping,
        tools.validate_address,
        tools.open_incident,
        tools.update_order_status,
        tools.calculate_delay_days,
    ],
)

# Expõe como servidor A2A via FastA2A
# Agent Card em: GET /.well-known/agent-card.json
# Endpoint A2A:  POST /  (JSON-RPC)
app = logistics_agent.to_a2a(
    name="logistics-agent",
    description="Rastreio de pedidos, ocorrências e frete reverso",
    version="1.0.0",
)

# uvicorn agents.logistics.agent:app --host 0.0.0.0 --port 8001
