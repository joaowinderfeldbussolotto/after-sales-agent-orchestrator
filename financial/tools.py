import httpx
from datetime import date
from pathlib import Path
from crewai.tools import tool

ORDERS_API = "http://mock-api:8003"


# ── DETERMINÍSTICAS ──────────────────────────────────────────────────────────

@tool("Verificar Elegibilidade CDC")
def check_cdc_eligibility(order_date: str, return_reason: str) -> dict:
    """Verifica se um pedido é elegível para devolução conforme o CDC brasileiro.

    Args:
        order_date: Data do pedido no formato YYYY-MM-DD
        return_reason: Motivo da devolução. Valores: 'arrependimento', 'defeito', 'erro_envio'

    Returns:
        dict com eligible (bool), days_since_purchase (int), rule_applied (str), reason (str)
    """
    purchased = date.fromisoformat(order_date)
    today = date.today()
    days_since = (today - purchased).days

    if return_reason in ("defeito", "erro_envio"):
        eligible = days_since <= 90
        rule = "CDC Art. 26 — 90 dias para produto durável com defeito"
    else:
        eligible = days_since <= 7
        rule = "CDC Art. 49 — 7 dias para arrependimento em compra à distância"

    return {
        "eligible": eligible,
        "days_since_purchase": days_since,
        "return_reason": return_reason,
        "rule_applied": rule,
        "reason": f"{'Elegível' if eligible else 'Fora do prazo'}. {rule}.",
    }


@tool("Calcular Valor de Reembolso")
def calculate_refund_amount(items_total: float, freight_paid: float, return_reason: str) -> dict:
    """Calcula o valor exato do reembolso conforme regras do e-commerce e CDC.

    Args:
        items_total: Valor total dos itens do pedido em R$
        freight_paid: Valor do frete pago pelo cliente em R$
        return_reason: Motivo: 'arrependimento', 'defeito', 'erro_envio'

    Returns:
        dict com refund_amount, breakdown e note explicativa
    """
    if return_reason == "arrependimento":
        refund = items_total
        note = "Frete original não reembolsado em caso de arrependimento (CDC Art. 49)"
        freight_included = False
    else:
        refund = items_total + freight_paid
        note = "Reembolso total incluindo frete (responsabilidade do vendedor)"
        freight_included = True

    return {
        "refund_amount": round(refund, 2),
        "items_total": items_total,
        "freight_paid": freight_paid,
        "freight_included": freight_included,
        "note": note,
    }


# ── EFEITOS COLATERAIS ───────────────────────────────────────────────────────

@tool("Emitir Reembolso")
def issue_refund(order_id: str, amount: float, method: str) -> dict:
    """Processa o reembolso de um pedido no sistema financeiro.

    Args:
        order_id: ID do pedido (ex: PV-2026-00142)
        amount: Valor do reembolso em R$
        method: Método de reembolso: 'credit_card', 'pix' ou 'voucher'

    Returns:
        dict com refund_id, status e estimated_days
    """
    r = httpx.post(
        f"{ORDERS_API}/orders/{order_id}/refund",
        json={"amount": amount, "method": method},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


@tool("Gerar Voucher de Compensação")
def generate_voucher(customer_id: str, value: float, reason: str) -> dict:
    """Gera um voucher de desconto como compensação ao cliente.

    Args:
        customer_id: ID do cliente (ex: CUST-001)
        value: Valor do voucher em R$
        reason: Motivo da compensação (ex: 'atraso_entrega', 'produto_com_defeito')

    Returns:
        dict com voucher_code, value, expires_days
    """
    r = httpx.post(
        f"{ORDERS_API}/vouchers",
        json={"customer_id": customer_id, "value": value, "reason": reason, "expires_days": 30},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


@tool("Consultar Direitos do Consumidor")
def get_consumer_rights(query: str) -> str:
    """Retorna o conteúdo completo do Código de Defesa do Consumidor (CDC) brasileiro.

    Args:
        query: Tema consultado (usado apenas para contexto do agente)
    """
    cdc_path = Path(__file__).parent / "cdc.md"
    return cdc_path.read_text(encoding="utf-8")
