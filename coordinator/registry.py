import os
import httpx

# Agent registry: URLs come from env vars; routing rules come from each agent's
# own description field in its Agent Card — no logic is hardcoded here.
# To onboard a new agent: add its URL below and write self-describing rules
# in the description field of its Agent Card.
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
        "card_path": "/a2a/agents/financial-agent/.well-known/agent-card.json",
        "protocol": "agno-rest",
    },
]

# name → {card, base_url, protocol}
AGENT_REGISTRY: dict[str, dict] = {}


async def discover_agents() -> str:
    """Fetch Agent Cards, populate AGENT_REGISTRY, return formatted prompt section.

    Each agent's description field is treated as a self-contained system prompt
    block for the coordinator — it declares when the agent should be triggered,
    what context to pass, and any escalation rules. The coordinator injects this
    verbatim so routing logic lives entirely in the agents, not here.
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
                    "protocol": config["protocol"],
                }
                name = card.get("name", config["name"])
                description = card.get("description", "Sem descrição.")
                lines.append(f"### {name} — Online")
                lines.append(description)
                lines.append("")
            except Exception as e:
                lines.append(f"### {config['name']} — Offline ({type(e).__name__})\n")

    return "\n".join(lines)
