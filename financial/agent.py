import uuid
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from crewai import Agent, Crew, Task, LLM
from crewai.a2a import A2AServerConfig

from .tools import (
    check_cdc_eligibility,
    calculate_refund_amount,
    issue_refund,
    generate_voucher,
    get_consumer_rights,
)

# ── LLM via Groq ──────────────────────────────────────────────────────────────
llm = LLM(model="groq/openai/gpt-oss-20b", temperature=0)

# ── Agent com A2AServerConfig ─────────────────────────────────────────────────
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
        issue_refund,
        generate_voucher,
        get_consumer_rights,
    ],
    a2a=A2AServerConfig(
        url="http://financial:8002",
        name="financial-agent",
        description="Reembolsos, vouchers e direitos do consumidor (CDC)",
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
    result = crew.kickoff()
    return str(result)


# ── FastAPI + endpoints A2A ───────────────────────────────────────────────────
# CrewAI com A2AServerConfig gera o Agent Card mas não provê servidor ASGI pronto.
# Implementamos os endpoints A2A manualmente. CrewAI é síncrono — retorna direto.

app = FastAPI(title="Financial Agent A2A Server")

TASKS: dict[str, dict] = {}


@app.get("/.well-known/agent-card.json")
def agent_card():
    """Discovery A2A — retorna o Agent Card com metadados de roteamento."""
    card = financial_agent.a2a.to_agent_card(url="http://financial:8002")
    data = card.model_dump()
    data["x_routing"] = {
        "triggers": [
            "Solicitação de reembolso ou estorno de pagamento",
            "Pedido de voucher ou compensação por má experiência",
            "Dúvidas sobre direitos do consumidor ou CDC",
            "Produto com defeito dentro do prazo de garantia",
            "Escalação do agente logístico (atraso grave ou escalate_financial=true)",
        ],
        "required_context": [
            "order_id",
            "order_date",
            "items_total",
            "freight_paid",
            "payment_method",
            "return_reason",
        ],
        "escalation_hint": None,
    }
    return data


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
