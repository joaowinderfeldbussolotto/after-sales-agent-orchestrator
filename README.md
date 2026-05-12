# PostVenda AI — After-Sales Multi-Agent Orchestrator

PostVenda AI is a reference implementation of an **after-sales orchestration system** for Brazilian e-commerce.
It coordinates specialized AI agents to handle common post-purchase scenarios (delivery issues, refund flows, compensation, and consumer-rights guidance) with a single chat entry point.

## What problem this solves

E-commerce after-sales workflows are usually fragmented:
- delivery data lives in one place,
- financial operations in another,
- legal guidance is inconsistent,
- and support teams must manually coordinate all steps.

This repository implements a practical architecture to solve that by:
- using one coordinator agent as the customer-facing brain,
- delegating domain work to specialized agents,
- centralizing order operations behind one MCP server,
- and returning a single consolidated answer to the customer.

## What was implemented

The system runs as six services:

| Service | Purpose | Tech | Port |
|---|---|---|---|
| **frontend** | Chat UI for interacting with the coordinator | `langchain-ai/agent-chat-ui` (Next.js, cloned in Docker build) | 3000 |
| **coordinator** | Main orchestrator agent; fetches order context and delegates to specialists | LangGraph + LangChain `create_agent` + Groq | 2024 |
| **logistics** | Specialist for tracking, delay analysis, incident opening, reverse-shipping quote/address checks | PydanticAI + FastA2A | 8001 |
| **financial** | Specialist for refund eligibility, refund amount, vouchers, and CDC guidance | Agno AgentOS + A2A interface | 8002 |
| **orders-mcp** | Central MCP tool gateway for all order read/write operations | FastMCP | 8004 |
| **mock-api** | In-memory source of truth for orders/incidents/refunds/vouchers | FastAPI | 8003 |

### High-level architecture

![PostVenda AI Architecture](assets/post-sales-agent-orchestrator.png)

```
Browser (3000)
   │
   ▼
Coordinator (2024)
   ├─ A2A JSON-RPC ─► Logistics (8001)
   ├─ A2A REST     ─► Financial (8002)
   └─ MCP tools    ─► Orders MCP (8004) ─► Mock API (8003)
```

## Why this architecture

### 1) Central MCP (`orders-mcp`)
A single MCP server exposes tool operations used across agents:
- `fetch_order`
- `fetch_refund_eligibility`
- `open_incident`
- `update_order_status`
- `issue_refund`
- `generate_voucher`

Why:
- avoids duplicated direct HTTP integration in each agent,
- makes data access patterns uniform,
- allows least-privilege tool exposure per agent,
- simplifies adding new agents later.

### 2) Specialized agents + coordinator
The coordinator focuses on intent routing and conversation quality; specialists focus on domain logic.

Why:
- better separation of concerns,
- easier evolution per domain,
- clearer operational ownership.

### 3) Protocol-aware delegation
The coordinator supports two A2A variants in one flow:
- **Logistics** via JSON-RPC (`message/send` + `tasks/get` polling)
- **Financial** via Agno REST endpoint (`/v1/message:send`)

Why:
- demonstrates interoperability with heterogeneous A2A implementations.

## How the orchestration works in practice

1. Customer sends a message in the chat UI.
2. Coordinator identifies `order_id` context and calls `fetch_order` via MCP.
3. Coordinator decides whether to answer directly or delegate using `delegate(...)`.
4. Selected specialist executes domain tools and business logic.
5. Specialist response is returned to coordinator.
6. Coordinator sends a consolidated customer-facing reply.

## Agent responsibilities and boundaries

### Coordinator (LangGraph)
- Loads specialist discovery info from each agent card at startup.
- Injects discovered routing guidance into system prompt.
- Uses only MCP `fetch_order` + `delegate` tool for orchestration.
- Applies retry middleware for model and tool HTTP failures.

### Logistics agent (PydanticAI)
Domain behaviors implemented:
- mock package tracking (`track_package`),
- delay calculation (`calculate_delay_days`),
- incident creation via MCP (`open_incident`),
- status update via MCP (`update_order_status`),
- reverse-shipping quote and address validation.

MCP access is filtered to logistics write operations only.

### Financial agent (Agno)
Domain behaviors implemented:
- CDC eligibility check (`check_cdc_eligibility`),
- refund amount calculation (`calculate_refund_amount`),
- CDC knowledge retrieval from local `cdc.md` (`get_consumer_rights`),
- refund/voucher execution via MCP tools.

## API/tool ownership model

| Capability | Owner |
|---|---|
| Order lookup | Orders MCP (`fetch_order`) |
| Refund eligibility metadata | Orders MCP (`fetch_refund_eligibility`) |
| Open logistics incident | Orders MCP (`open_incident`) |
| Update order status | Orders MCP (`update_order_status`) |
| Issue refund | Orders MCP (`issue_refund`) |
| Generate voucher | Orders MCP (`generate_voucher`) |
| Delay/track/address/reverse-shipping logic | Logistics agent local tools |
| CDC legal rules/refund math/content guidance | Financial agent local tools |

## Data model and scenarios included

The mock API ships with 3 seeded orders in `mock-api/data.py`:
- `PV-2026-00142`: delayed shipment scenario,
- `PV-2026-00099`: regret return scenario,
- `PV-2026-00210`: product defect scenario.

State is in-memory for:
- `INCIDENTS`,
- `REFUNDS`,
- `VOUCHERS`.

This is a demo environment (non-persistent by design).

## Quick start

### 1) Prerequisites
- Docker + Docker Compose
- Groq API key
- (Optional) Langfuse keys for tracing

### 2) Configure environment

```bash
# from the repository root
cp .env.example .env
# fill GROQ_API_KEY
# optional: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, model/timeouts overrides
```

### 3) Build and run

```bash
docker compose up --build
```

### 4) Open UI
- Open `http://localhost:3000`
- In agent-chat-ui sidebar:
  - `Deployment URL`: `http://localhost:2024`
  - `Assistant ID`: `coordinator`

## Example prompts to test

- Delayed delivery with compensation intent:
  - `My order PV-2026-00142 is late. What happened and what can be done?`
- Regret return:
  - `I want to return order PV-2026-00099 because I changed my mind.`
- Defect rights:
  - `Order PV-2026-00210 arrived defective. What are my rights?`

## Direct endpoint checks

```bash
# Coordinator
curl http://localhost:2024/ok

# Logistics agent card
curl http://localhost:8001/.well-known/agent-card.json

# Financial agent card
curl http://localhost:8002/a2a/agents/financial-agent/.well-known/agent-card.json

# Mock order
curl http://localhost:8003/orders/PV-2026-00142

# MCP tools list
curl -X POST http://localhost:8004/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Environment variables (main)

From `.env.example`:
- `GROQ_API_KEY` (required)
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` (optional)
- `COORDINATOR_MODEL`, `LOGISTICS_MODEL`, `FINANCIAL_MODEL` (optional)
- `A2A_TIMEOUT`, `A2A_AGNO_TIMEOUT`, `A2A_POLL_TIMEOUT`, `MCP_HTTP_TIMEOUT`, `REGISTRY_TIMEOUT` (optional)

## Observability

When Langfuse keys are provided:
- coordinator traces through Langfuse LangChain callback,
- logistics via PydanticAI instrumentation,
- financial via OpenTelemetry exporter + Agno instrumentation.

## Limitations (important)

- Demo-grade mock backend with in-memory state (no persistence).
- No authn/authz layer in exposed HTTP services.
- No production hardening (rate-limits, secrets management, HA, retries per upstream SLA, etc.).
- Prompting and outputs are primarily Portuguese-oriented in specialist instructions.

## Repository structure

```
after-sales-agent-orchestrator/
├── README.md
├── .env.example
├── docker-compose.yml
├── assets/
├── frontend/
├── coordinator/
├── logistics/
├── financial/
├── orders-mcp/
└── mock-api/
```

## Summary

This project demonstrates a concrete, working pattern for **multi-agent after-sales orchestration**:
- one orchestrator,
- multiple specialist agents,
- one shared MCP data gateway,
- and a UI for end-to-end support interactions.

If your goal is to prototype or evolve AI-assisted support workflows for post-purchase operations, this repository gives you a practical baseline to adapt.
