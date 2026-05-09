from fastapi import FastAPI, HTTPException
from datetime import date, datetime
import uuid

from data import ORDERS, INCIDENTS, REFUNDS, VOUCHERS

app = FastAPI(title="PostVenda Mock API", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "orders": len(ORDERS)}


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    if order_id not in ORDERS:
        raise HTTPException(404, f"Pedido {order_id} não encontrado")
    return ORDERS[order_id]


@app.get("/orders/{order_id}/items")
def get_order_items(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(404)
    return order["items"]


@app.get("/orders/{order_id}/refund-eligibility")
def get_refund_eligibility(order_id: str):
    order = ORDERS.get(order_id)
    if not order:
        raise HTTPException(404)
    order_date = date.fromisoformat(order["order_date"])
    days = (date.today() - order_date).days
    return {
        "order_id": order_id,
        "order_date": order["order_date"],
        "days_since_purchase": days,
        "within_7_days": days <= 7,
        "payment_method": order["payment_method"],
        "items_total": order["items_total"],
        "freight_paid": order["freight_paid"],
    }


@app.get("/customers/{cpf}/orders")
def get_customer_orders(cpf: str):
    customer_orders = [o for o in ORDERS.values() if o["cpf"] == cpf]
    return customer_orders


@app.post("/orders/{order_id}/incident")
def open_incident(order_id: str, body: dict):
    if order_id not in ORDERS:
        raise HTTPException(404)
    incident = {
        "incident_id": str(uuid.uuid4())[:8].upper(),
        "order_id": order_id,
        "reason": body.get("reason"),
        "created_at": datetime.now().isoformat(),
        "status": "open",
    }
    INCIDENTS.append(incident)
    ORDERS[order_id]["status"] = "incident_opened"
    return incident


@app.put("/orders/{order_id}/status")
def update_status(order_id: str, body: dict):
    if order_id not in ORDERS:
        raise HTTPException(404)
    ORDERS[order_id]["status"] = body.get("status")
    return {"order_id": order_id, "status": ORDERS[order_id]["status"]}


@app.post("/orders/{order_id}/refund")
def issue_refund(order_id: str, body: dict):
    if order_id not in ORDERS:
        raise HTTPException(404)
    refund = {
        "refund_id": f"REF-{str(uuid.uuid4())[:8].upper()}",
        "order_id": order_id,
        "amount": body.get("amount"),
        "method": body.get("method"),
        "created_at": datetime.now().isoformat(),
        "status": "processing",
        "estimated_days": 5 if body.get("method") == "credit_card" else 1,
    }
    REFUNDS.append(refund)
    ORDERS[order_id]["status"] = "refund_requested"
    return refund


@app.post("/vouchers")
def generate_voucher(body: dict):
    voucher = {
        "voucher_code": f"PV{str(uuid.uuid4())[:6].upper()}",
        "customer_id": body.get("customer_id"),
        "value": body.get("value"),
        "reason": body.get("reason"),
        "expires_days": body.get("expires_days", 30),
        "created_at": datetime.now().isoformat(),
        "status": "active",
    }
    VOUCHERS.append(voucher)
    return voucher
