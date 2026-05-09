import httpx
from datetime import date

ORDERS_API = "http://mock-api:8003"


# ── MOCK MCPs ────────────────────────────────────────────────────────────────

def track_package(tracking_code: str) -> dict:
    """Rastreia um pacote pelos Correios e retorna histórico de eventos. [MOCK]

    Args:
        tracking_code: Código de rastreio (ex: SB123456789BR)
    """
    if tracking_code.startswith("SB"):
        return {
            "tracking_code": tracking_code,
            "carrier": "Correios SEDEX",
            "status": "in_transit",
            "last_event": "Objeto em trânsito - de Curitiba/PR para São Paulo/SP",
            "last_update": "2026-05-05T14:32:00",
            "estimated_delivery": "2026-05-07",
            "events": [
                {"date": "2026-05-05T14:32", "location": "Curitiba/PR", "desc": "Em trânsito para destino"},
                {"date": "2026-05-04T09:10", "location": "Curitiba/PR", "desc": "Saiu para entrega"},
                {"date": "2026-05-03T18:00", "location": "Porto Alegre/RS", "desc": "Chegou na unidade"},
                {"date": "2026-05-02T10:00", "location": "Porto Alegre/RS", "desc": "Objeto postado"},
            ],
        }
    elif tracking_code.startswith("PA"):
        return {
            "tracking_code": tracking_code,
            "carrier": "Correios PAC",
            "status": "delivered",
            "last_event": "Objeto entregue ao destinatário",
            "last_update": "2026-04-30T11:20:00",
            "events": [
                {"date": "2026-04-30T11:20", "location": "São Paulo/SP", "desc": "Entregue"},
            ],
        }
    return {"tracking_code": tracking_code, "status": "not_found", "events": []}


def quote_reverse_shipping(cep: str, weight_kg: float) -> dict:
    """Cotação de frete reverso via Melhor Envio para devolução. [MOCK]

    Args:
        cep: CEP de origem da devolução (somente números, 8 dígitos)
        weight_kg: Peso estimado do pacote em kg
    """
    base = 12.0 + (weight_kg * 3.5)
    return {
        "origin_cep": cep,
        "weight_kg": weight_kg,
        "options": [
            {
                "carrier": "Correios PAC",
                "price": round(base, 2),
                "days": 7,
                "description": "Coleta em domicílio ou postagem em agência",
            },
            {
                "carrier": "Jadlog .Package",
                "price": round(base * 1.4, 2),
                "days": 3,
                "description": "Coleta em domicílio",
            },
        ],
        "note": "Frete reverso por conta do e-commerce em caso de defeito ou erro de envio",
    }


def validate_address(cep: str) -> dict:
    """Valida e expande um CEP brasileiro via ViaCEP. [MOCK]

    Args:
        cep: CEP com 8 dígitos (somente números)
    """
    ceps = {
        "01310100": {"logradouro": "Av. Paulista", "bairro": "Bela Vista", "cidade": "São Paulo", "uf": "SP"},
        "80010020": {"logradouro": "R. XV de Novembro", "bairro": "Centro", "cidade": "Curitiba", "uf": "PR"},
    }
    cep_clean = cep.replace("-", "").replace(" ", "")
    data = ceps.get(
        cep_clean,
        {"logradouro": "Rua Simulada", "bairro": "Bairro Exemplo", "cidade": "São Paulo", "uf": "SP"},
    )
    return {"cep": cep_clean, "valid": True, **data}


# ── EFEITOS COLATERAIS (Mock API) ────────────────────────────────────────────

def open_incident(order_id: str, reason: str) -> dict:
    """Abre uma ocorrência logística para um pedido na transportadora.

    Args:
        order_id: ID do pedido (ex: PV-2026-00142)
        reason: Motivo da ocorrência (ex: 'atraso', 'extravio', 'avaria')
    """
    r = httpx.post(
        f"{ORDERS_API}/orders/{order_id}/incident",
        json={"reason": reason},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


def update_order_status(order_id: str, status: str) -> dict:
    """Atualiza o status de um pedido no sistema.

    Args:
        order_id: ID do pedido
        status: Novo status (ex: 'incident_opened', 'returning', 'lost')
    """
    r = httpx.put(
        f"{ORDERS_API}/orders/{order_id}/status",
        json={"status": status},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


# ── DETERMINÍSTICAS ──────────────────────────────────────────────────────────

def calculate_delay_days(expected_date: str, carrier_status: str) -> dict:
    """Calcula quantos dias de atraso uma entrega possui.

    Args:
        expected_date: Data prevista de entrega no formato YYYY-MM-DD
        carrier_status: Status atual retornado pelo rastreio (ex: 'in_transit', 'delivered')
    """
    if carrier_status == "delivered":
        return {"delayed": False, "days": 0, "message": "Pedido já entregue"}

    expected = date.fromisoformat(expected_date)
    today = date.today()
    delta = (today - expected).days

    if delta <= 0:
        return {
            "delayed": False,
            "days": 0,
            "days_remaining": abs(delta),
            "message": f"No prazo. Restam {abs(delta)} dia(s) para entrega.",
        }

    return {
        "delayed": True,
        "days": delta,
        "expected_date": expected_date,
        "today": str(today),
        "message": f"Entrega atrasada há {delta} dia(s).",
        "escalate_financial": delta > 3,
    }
