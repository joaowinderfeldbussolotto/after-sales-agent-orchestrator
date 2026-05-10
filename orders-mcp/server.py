import os
from fastmcp import FastMCP
import httpx

ORDERS_API = os.getenv("ORDERS_API_URL", "http://mock-api:8003")

mcp = FastMCP("orders-mcp")


# ── Tools de LEITURA ──────────────────────────────────────────────────────────

@mcp.tool()
async def fetch_order(order_id: str) -> dict:
    """Busca dados completos de um pedido pelo ID.

    Args:
        order_id: ID do pedido (ex: PV-2026-00142)
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{ORDERS_API}/orders/{order_id}", timeout=10.0)
        if r.status_code == 404:
            return {"error": f"Pedido {order_id} não encontrado"}
        return r.json()


@mcp.tool()
async def fetch_refund_eligibility(order_id: str) -> dict:
    """Verifica elegibilidade para reembolso ou devolução de um pedido.

    Args:
        order_id: ID do pedido
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{ORDERS_API}/orders/{order_id}/refund-eligibility",
            timeout=10.0,
        )
        if r.status_code == 404:
            return {"error": f"Pedido {order_id} não encontrado"}
        return r.json()


# ── Tools de ESCRITA LOGÍSTICA ────────────────────────────────────────────────

@mcp.tool()
async def open_incident(order_id: str, reason: str) -> dict:
    """Abre uma ocorrência logística para um pedido.

    Args:
        order_id: ID do pedido
        reason: Motivo da ocorrência (ex: 'atraso', 'extravio', 'avaria')
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{ORDERS_API}/orders/{order_id}/incident",
            json={"reason": reason},
            timeout=10.0,
        )
        return r.json()


@mcp.tool()
async def update_order_status(order_id: str, status: str) -> dict:
    """Atualiza o status de um pedido.

    Args:
        order_id: ID do pedido
        status: Novo status (ex: 'incident_opened', 'returning', 'lost')
    """
    async with httpx.AsyncClient() as client:
        r = await client.put(
            f"{ORDERS_API}/orders/{order_id}/status",
            json={"status": status},
            timeout=10.0,
        )
        return r.json()


# ── Tools de ESCRITA FINANCEIRA ───────────────────────────────────────────────

@mcp.tool()
async def issue_refund(order_id: str, amount: float, method: str) -> dict:
    """Processa o reembolso de um pedido.

    Args:
        order_id: ID do pedido
        amount: Valor do reembolso em R$
        method: Método: 'credit_card', 'pix' ou 'voucher'
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{ORDERS_API}/orders/{order_id}/refund",
            json={"amount": amount, "method": method},
            timeout=10.0,
        )
        return r.json()


@mcp.tool()
async def generate_voucher(customer_id: str, value: float, reason: str) -> dict:
    """Gera um voucher de compensação para o cliente.

    Args:
        customer_id: ID do cliente (ex: CUST-001)
        value: Valor do voucher em R$
        reason: Motivo da compensação
    """
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{ORDERS_API}/vouchers",
            json={
                "customer_id": customer_id,
                "value": value,
                "reason": reason,
                "expires_days": 30,
            },
            timeout=10.0,
        )
        return r.json()


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8004)
