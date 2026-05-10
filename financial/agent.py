import os

from agno.agent import Agent
from agno.models.groq import Groq
from agno.os import AgentOS
from agno.tools.mcp import MCPTools

from .tools import check_cdc_eligibility, calculate_refund_amount, get_consumer_rights

MCP_URL = os.getenv("ORDERS_MCP_URL", "http://orders-mcp:8004/mcp")

financial_agent = Agent(
    id="financial-agent",
    name="financial-agent",
    model=Groq(id="openai/gpt-oss-20b"),
    tools=[
        check_cdc_eligibility,
        calculate_refund_amount,
        get_consumer_rights,
        MCPTools(transport="streamable-http", url=MCP_URL),
    ],
    description="""Especialista em reembolsos, vouchers e direitos do consumidor (CDC).

ACIONAR QUANDO:
- Solicitação de reembolso ou estorno de pagamento
- Pedido de voucher ou compensação por má experiência
- Dúvidas sobre direitos do consumidor ou CDC
- Produto com defeito dentro do prazo de garantia
- Escalação do agente logístico (atraso grave ou escalate_financial=true)

CONTEXTO NECESSÁRIO AO DELEGAR: order_id, order_date, items_total, freight_paid, payment_method, return_reason

ESCALAÇÃO: Nenhuma — agente terminal do fluxo financeiro""",
        version="1.0.0",
    ),
    verbose=True,
)


def run_financial_task(task_description: str) -> str:
    """Executa a Crew com uma task dinâmica e retorna o resultado."""
    task = Task(
        description=task_description,
        expected_output=(
            "JSON com: "
            "- action_taken: ação realizada "
            "- cdc_eligible: elegibilidade CDC "
            "- refund_amount: valor do reembolso (se aplicável) "
            "- refund_id ou voucher_code: identificador da compensação "
            "- consumer_rights: direitos aplicáveis "
            "- message: resposta humanizada para o cliente"
        ),
        agent=financial_agent,
    )
    crew = Crew(agents=[financial_agent], tasks=[task], verbose=True)
    with langfuse.start_as_current_observation(as_type="span", name="financial-agent-run"):
        result = crew.kickoff()
    langfuse.flush()
    return str(result)


# ── FastAPI + endpoints A2A ───────────────────────────────────────────────────
# CrewAI com A2AServerConfig gera o Agent Card mas não provê servidor ASGI pronto.
# Implementamos os endpoints A2A manualmente. CrewAI é síncrono — retorna direto.

app = FastAPI(title="Financial Agent A2A Server")

CONTEXTO NECESSÁRIO AO DELEGAR: order_id, return_reason

O agente busca por conta própria todas as demais informações do pedido
(order_date, items_total, freight_paid, payment_method) via suas tools.""",
    instructions="""Você é especialista em direito do consumidor brasileiro e processos
financeiros de e-commerce. Conhece o CDC profundamente e sabe calcular
reembolsos com precisão. Sempre verifique elegibilidade antes de processar
qualquer reembolso.

Use apenas as ferramentas relevantes ao domínio financeiro:
- Para consultar pedido: fetch_order, fetch_refund_eligibility
- Para processar compensação: issue_refund, generate_voucher
- Para avaliar elegibilidade: check_cdc_eligibility, calculate_refund_amount
- Para orientar sobre direitos: get_consumer_rights

Responda sempre em português com uma mensagem humanizada ao cliente.""",
)

agent_os = AgentOS(
    agents=[financial_agent],
    a2a_interface=True,
)

app = agent_os.get_app()
