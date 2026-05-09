import os
import httpx

# PydanticAI (FastA2A) and CrewAI both expose Agent Card at /.well-known/agent-card.json
# and accept JSON-RPC at POST /
AGENT_CONFIGS = [
    {
        "name": "logistics-agent",
        "base_url": os.getenv("LOGISTICS_URL", "http://logistics:8001"),
        "card_path": "/.well-known/agent-card.json",
        "protocol": "json-rpc",
    },
    {
        "name": "financial-agent",
        "base_url": os.getenv("FINANCIAL_URL", "http://financial:8002"),
        "card_path": "/.well-known/agent-card.json",
        "protocol": "json-rpc",
    },
]

# name → {card, base_url, protocol}
AGENT_REGISTRY: dict[str, dict] = {}


async def discover_agents() -> str:
    """GET Agent Cards for all configured agents, populate AGENT_REGISTRY, return prompt string."""
    lines = ["## Agentes Especializados Disponíveis\n"]

    async with httpx.AsyncClient(timeout=3.0) as client:
        for config in AGENT_CONFIGS:
            url = f"{config['base_url']}{config['card_path']}"
            try:
                r = await client.get(url)
                card = r.json()
                AGENT_REGISTRY[config["name"]] = {
                    "card": card,
                    "base_url": config["base_url"],
                    "protocol": config["protocol"],
                }
                skills = card.get("skills", [])
                skill_names = [s.get("name", s) if isinstance(s, dict) else s for s in skills]
                lines.append(f"**{card.get('name', config['name'])}**")
                lines.append(f"  Descrição: {card.get('description', 'N/A')}")
                lines.append(f"  Skills: {', '.join(skill_names) or 'N/A'}")
                lines.append(f"  Status: Online\n")
            except Exception as e:
                lines.append(f"**{config['name']}** — Offline ({type(e).__name__})\n")

    return "\n".join(lines)
