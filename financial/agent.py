import base64
import os

from agno.agent import Agent
from agno.models.groq import Groq
from agno.os import AgentOS
from agno.tools.mcp import MCPTools
from openinference.instrumentation.agno import AgnoInstrumentor
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from .tools import check_cdc_eligibility, calculate_refund_amount, get_consumer_rights

MCP_URL = os.getenv("ORDERS_MCP_URL", "http://orders-mcp:8004/mcp")


def _configure_langfuse_tracing() -> None:
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    if not public_key or not secret_key:
        return

    langfuse_auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        os.getenv("LANGFUSE_OTLP_ENDPOINT", "https://us.cloud.langfuse.com/api/public/otel"),
    )
    os.environ.setdefault(
        "OTEL_EXPORTER_OTLP_HEADERS",
        f"Authorization=Basic {langfuse_auth}",
    )

    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
    trace_api.set_tracer_provider(tracer_provider=tracer_provider)

    AgnoInstrumentor().instrument()


_configure_langfuse_tracing()

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
- Quando o cliente está insatisfeito com atrasos na entrega e solicita compensação pela demora

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
