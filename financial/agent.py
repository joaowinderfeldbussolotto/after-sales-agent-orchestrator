import os
import uuid
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from crewai import Agent, Crew, Task, LLM
from crewai.a2a import A2AServerConfig
from crewai_tools import MCPServerAdapter
from langfuse import Langfuse, get_client
from openinference.instrumentation.crewai import CrewAIInstrumentor

Langfuse()
CrewAIInstrumentor().instrument(skip_dep_check=True)
langfuse = get_client()

from .tools import (
    check_cdc_eligibility,
    calculate_refund_amount,
    get_consumer_rights,
)

MCP_URL = os.getenv("ORDERS_MCP_URL", "http://orders-mcp:8004/mcp")

# Tools MCP que o financeiro pode acessar.
FINANCIAL_ALLOWED_TOOLS = {
    "fetch_order",
    "fetch_refund_eligibility",
    "issue_refund",
    "generate_voucher",
}

# ── LLM via Groq ──────────────────────────────────────────────────────────────
llm = LLM(model="groq/openai/gpt-oss-20b", temperature=0)

# ── Agent placeholder — usado APENAS para servir o Agent Card A2A ─────────────
# O agente real (com tools MCP) é construído dentro de run_financial_task,
# pois o MCPServerAdapter precisa viver dentro de um context manager.
financial_agent = Agent(
    role="Agente Financeiro de Pós-Venda",
    goal="Processar reembolsos, gerar vouchers e orientar clientes sobre direitos do consumidor",
    backstory=(
        "Você é especialista em direito do consumidor brasileiro e processos "
        "financeiros de e-commerce. Conhece o CDC profundamente e sabe calcular "
        "reembolsos com precisão. Sempre verifica elegibilidade antes de processar "
        "qualquer reembolso."
    ),
    llm=llm,
    tools=[
        check_cdc_eligibility,
        calculate_refund_amount,
        get_consumer_rights,
    ],
    a2a=A2AServerConfig(
        url="http://financial:8002",
        name="financial-agent",
        description="""Especialista em reembolsos, vouchers e direitos do consumidor (CDC).

ACIONAR QUANDO:
- Solicitação de reembolso ou estorno de pagamento
- Pedido de voucher ou compensação por má experiência
- Dúvidas sobre direitos do consumidor ou CDC
- Produto com defeito dentro do prazo de garantia

CONTEXTO NECESSÁRIO AO DELEGAR: order_id, return_reason

O agente busca por conta própria todas as demais informações do pedido
(order_date, items_total, freight_paid, payment_method) via suas tools.""",
        version="1.0.0",
    ),
    verbose=True,
)


def run_financial_task(task_description: str) -> str:
    """Executa a Crew com uma task dinâmica e retorna o resultado.

    Constrói um Agent fresco a cada chamada porque o MCPServerAdapter precisa
    viver dentro de um context manager.
    """
    server_params = {"url": MCP_URL, "transport": "streamable-http"}

    with MCPServerAdapter(server_params) as mcp_tools:
        filtered_mcp = [t for t in mcp_tools if t.name in FINANCIAL_ALLOWED_TOOLS]
        all_tools = [
            check_cdc_eligibility,
            calculate_refund_amount,
            get_consumer_rights,
            *filtered_mcp,
        ]

        agent_with_mcp = Agent(
            role=financial_agent.role,
            goal=financial_agent.goal,
            backstory=financial_agent.backstory,
            llm=llm,
            tools=all_tools,
            verbose=True,
        )

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
            agent=agent_with_mcp,
        )
        crew = Crew(agents=[agent_with_mcp], tasks=[task], verbose=True)

        with langfuse.start_as_current_observation(as_type="span", name="financial-agent-run"):
            result = crew.kickoff()

        langfuse.flush()
        return str(result)


# ── FastAPI + endpoints A2A ───────────────────────────────────────────────────

app = FastAPI(title="Financial Agent A2A Server")

TASKS: dict[str, dict] = {}


@app.get("/.well-known/agent-card.json")
def agent_card():
    """Discovery A2A — retorna o Agent Card."""
    card = financial_agent.a2a
    return card.model_dump()


@app.post("/")
async def handle_a2a(request: Request):
    """Endpoint JSON-RPC para protocolo A2A."""
    body = await request.json()
    method = body.get("method")
    params = body.get("params", {})
    rpc_id = body.get("id", "1")

    if method == "message/send":
        message = params.get("message", {})
        parts = message.get("parts", [])
        task_text = " ".join(p.get("text", "") for p in parts if p.get("kind") == "text")

        result = run_financial_task(task_text)
        task_id = str(uuid.uuid4())

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "id": task_id,
                "contextId": message.get("contextId", str(uuid.uuid4())),
                "status": {"state": "completed", "timestamp": datetime.utcnow().isoformat()},
                "artifacts": [{
                    "artifactId": str(uuid.uuid4()),
                    "parts": [{"kind": "text", "text": result}],
                }],
            },
        })

    elif method == "tasks/get":
        task_id = params.get("id")
        task = TASKS.get(task_id)
        if not task:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32001, "message": "Task not found"},
            })
        return JSONResponse({"jsonrpc": "2.0", "id": rpc_id, "result": task})

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method '{method}' not found"},
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
