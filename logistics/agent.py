import uuid
from datetime import datetime

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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

# ── Agent Card com metadados de roteamento auto-descritivos ───────────────────
# O coordenador lê x_routing para descobrir quando e como acionar este agente.
# Nenhuma regra de roteamento precisa ser hardcoded no coordenador.
AGENT_CARD = {
    "name": "logistics-agent",
    "description": "Especialista em rastreamento de pedidos, ocorrências logísticas e frete reverso.",
    "version": "1.0.0",
    "url": "http://logistics:8001",
    "capabilities": {"streaming": False},
    "skills": [
        {
            "id": "track-package",
            "name": "Rastrear Pedido",
            "description": "Rastreia o pacote via transportadora e retorna histórico de eventos",
        },
        {
            "id": "open-incident",
            "name": "Abrir Ocorrência",
            "description": "Registra ocorrência de atraso, extravio ou avaria na transportadora",
        },
        {
            "id": "reverse-shipping",
            "name": "Frete Reverso",
            "description": "Cota frete reverso para devolução de produto pelo cliente",
        },
        {
            "id": "validate-address",
            "name": "Validar Endereço",
            "description": "Valida e expande CEP para verificar endereço de entrega",
        },
    ],
    "x_routing": {
        "triggers": [
            "Cliente pergunta sobre rastreio, localização ou status da entrega",
            "Pedido com atraso ou prazo de entrega ultrapassado",
            "Solicitação de frete reverso ou coleta para devolução",
            "Abertura de ocorrência por extravio, avaria ou não entregue",
            "Validação ou problema com endereço de entrega",
        ],
        "required_context": [
            "order_id",
            "tracking_code",
            "expected_delivery",
            "current_status",
        ],
        "escalation_hint": (
            "Se a resposta contiver escalate_financial=true ou delay_days > 3, "
            "acionar também financial-agent com: order_id, order_date, items_total, "
            "freight_paid, payment_method e return_reason='atraso_entrega'"
        ),
    },
}


# ── FastAPI + endpoints A2A ───────────────────────────────────────────────────

app = FastAPI(title="Logistics Agent A2A Server")


@app.get("/.well-known/agent-card.json")
def agent_card():
    """Discovery A2A — retorna o Agent Card com metadados de roteamento."""
    return AGENT_CARD


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

        result = await logistics_agent.run(task_text)
        text_result = str(result.data)

        return JSONResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": {
                "id": str(uuid.uuid4()),
                "contextId": message.get("contextId", str(uuid.uuid4())),
                "status": {"state": "completed", "timestamp": datetime.utcnow().isoformat()},
                "artifacts": [{
                    "artifactId": str(uuid.uuid4()),
                    "parts": [{"kind": "text", "text": text_result}],
                }],
            },
        })

    return JSONResponse({
        "jsonrpc": "2.0",
        "id": rpc_id,
        "error": {"code": -32601, "message": f"Method '{method}' not found"},
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
