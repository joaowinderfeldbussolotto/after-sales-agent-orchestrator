import os
import httpx

# Agent registry: URLs come from env vars; all routing logic comes from Agent Cards.
# To onboard a new agent: add its URL here and implement x_routing in its Agent Card.
AGENT_CONFIGS = [
    {
        "name": "logistics-agent",
        "base_url": os.getenv("LOGISTICS_URL", "http://logistics:8001"),
        "card_path": "/.well-known/agent-card.json",
    },
    {
        "name": "financial-agent",
        "base_url": os.getenv("FINANCIAL_URL", "http://financial:8002"),
        "card_path": "/.well-known/agent-card.json",
    },
]

# name → {card, base_url}
AGENT_REGISTRY: dict[str, dict] = {}


async def discover_agents() -> str:
    """Fetch Agent Cards, populate AGENT_REGISTRY, return formatted prompt section.

    The returned string contains every agent's self-described routing rules
    (x_routing.triggers, required_context, escalation_hint) so the coordinator
    can make routing decisions purely from what agents declare about themselves.
    """
    lines = ["## Agentes Especializados Disponíveis\n"]

    async with httpx.AsyncClient(timeout=5.0) as client:
        for config in AGENT_CONFIGS:
            url = f"{config['base_url']}{config['card_path']}"
            try:
                r = await client.get(url)
                r.raise_for_status()
                card = r.json()
                AGENT_REGISTRY[config["name"]] = {
                    "card": card,
                    "base_url": config["base_url"],
                }

                routing = card.get("x_routing", {})
                triggers = routing.get("triggers", [])
                required = routing.get("required_context", [])
                escalation = routing.get("escalation_hint")

                lines.append(f"### {card.get('name', config['name'])} — Online")
                lines.append(f"**Descrição:** {card.get('description', 'N/A')}\n")

                if triggers:
                    lines.append("**Acionar quando:**")
                    for t in triggers:
                        lines.append(f"- {t}")
                    lines.append("")

                if required:
                    lines.append(f"**Contexto necessário ao delegar:** {', '.join(required)}\n")

                if escalation:
                    lines.append(f"**Regra de escalação:** {escalation}\n")

            except Exception as e:
                lines.append(f"### {config['name']} — Offline ({type(e).__name__})\n")

    return "\n".join(lines)
