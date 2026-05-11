from datetime import date

ORDERS: dict[str, dict] = {
    "PV-2026-00142": {
        "order_id": "PV-2026-00142",
        "customer_id": "CUST-001",
        "customer_name": "Maria Silva",
        "cpf": "123.456.789-00",
        "tracking_code": "SB123456789BR",
        "carrier": "correios",
        "modality": "SEDEX",
        "order_date": "2026-04-28",
        "expected_delivery": "2026-05-02",
        "status": "in_transit",
        "items": [
            {"sku": "TEN-001", "name": "Tênis Runner Pro", "qty": 1, "unit_price": 299.90}
        ],
        "items_total": 299.90,
        "freight_paid": 25.90,
        "total_value": 325.80,
        "payment_method": "credit_card",
    },
    "PV-2026-00099": {
        "order_id": "PV-2026-00099",
        "customer_id": "CUST-002",
        "customer_name": "João Souza",
        "cpf": "987.654.321-00",
        "tracking_code": "PA987654321BR",
        "carrier": "correios",
        "modality": "PAC",
        "order_date": "2026-04-20",
        "expected_delivery": "2026-04-30",
        "status": "delivered",
        "items": [
            {"sku": "CAM-003", "name": "Câmera de Segurança WiFi", "qty": 1, "unit_price": 189.00}
        ],
        "items_total": 189.00,
        "freight_paid": 0.00,
        "total_value": 189.00,
        "payment_method": "pix",
    },
    "PV-2026-00210": {
        "order_id": "PV-2026-00210",
        "customer_id": "CUST-003",
        "customer_name": "Ana Costa",
        "cpf": "111.222.333-44",
        "tracking_code": "SB999888777BR",
        "carrier": "correios",
        "modality": "SEDEX",
        "order_date": "2026-05-01",
        "expected_delivery": "2026-05-05",
        "status": "delivered",
        "items": [
            {"sku": "FNE-007", "name": "Fone Bluetooth Pro", "qty": 1, "unit_price": 149.90}
        ],
        "items_total": 149.90,
        "freight_paid": 15.90,
        "total_value": 165.80,
        "payment_method": "pix",
    },
}

INCIDENTS: list[dict] = []
REFUNDS: list[dict] = []
VOUCHERS: list[dict] = []
