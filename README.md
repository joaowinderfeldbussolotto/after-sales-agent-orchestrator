# PostVenda AI — Multi-Agent After-Sales Orchestrator

A multi-agent system for Brazilian e-commerce after-sales support, built with the **A2A protocol** (Agent-to-Agent). Three specialized agents collaborate to handle logistics issues, refunds, and consumer rights queries — all orchestrated by a central coordinator with a real-time chat interface.

## Architecture

```
Browser → http://localhost:3000  (Agent UI / Next.js)
            │  AG-UI protocol (SSE streaming)
            ▼
         http://localhost:8000  (Coordinator / Agno AgentOS)
            │
            ├── A2A → http://logistics:8001  (PydanticAI / FastA2A)
            └── A2A → http://financial:8002  (CrewAI / FastAPI)
                           │
                       Both read from:
                       http://mock-api:8003  (FastAPI mock orders service)
```

| Service | Framework | Model | Port |
|---|---|---|---|
| **Coordinator** | Agno (A2A Client + AgentOS) | `openai/gpt-oss-120b` via Groq | 8000 |
| **Logistics Agent** | PydanticAI (A2A Server) | `llama-3.3-70b-versatile` via Groq | 8001 |
| **Financial Agent** | CrewAI (A2A Server) | `openai/gpt-oss-20b` via Groq | 8002 |
| **Mock API** | FastAPI | — | 8003 |
| **Frontend** | Next.js (Agent UI) | — | 3000 |

## Quick Start

### 1. Prerequisites

- Docker + Docker Compose
- A free [Groq API key](https://console.groq.com)

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set your GROQ_API_KEY
```

### 3. Run

```bash
docker compose up --build
```

First run builds the FAISS index for the CDC RAG (runs once, ~2 min for sentence-transformers download).

Open **http://localhost:3000** in your browser to chat with the coordinator.

> The Agent UI sidebar lets you change the API URL. Set it to `http://localhost:8000` if it's not already.

## Example Inputs

Paste any of these into the Agent UI chat:

---

### Delayed order — triggers logistics + financial escalation

```
Meu pedido PV-2026-00142 devia ter chegado semana passada e até agora não chegou. O que está acontecendo?
```

**Expected flow:**
1. Coordinator fetches order `PV-2026-00142` (Maria Silva, Tênis Runner Pro, R$325,80)
2. Delegates to **logistics-agent** → tracks `SB123456789BR`, calculates 7+ day delay, opens incident `INC-XXXX`, flags `escalate_financial=true`
3. Escalates to **financial-agent** → verifies CDC eligibility, generates compensation voucher (~R$30)
4. Returns consolidated response with incident ID, voucher code, and updated delivery estimate

---

### Delivered order — refund request (regret)

```
Quero devolver o pedido PV-2026-00099. Comprei uma câmera mas não gostei, posso devolver?
```

**Expected flow:**
1. Coordinator fetches order `PV-2026-00099` (João Souza, Câmera WiFi, delivered via PAC)
2. Delegates to **financial-agent** → checks CDC Art. 49 (7-day regret window), calculates refund (R$189,00, freight not included), processes refund via PIX
3. Returns response with refund ID, amount, and estimated credit timeline

---

### Consumer rights query

```
Comprei o pedido PV-2026-00210 mas o fone veio com defeito. Quais são meus direitos?
```

**Expected flow:**
1. Coordinator fetches order `PV-2026-00210` (Ana Costa, Fone Bluetooth, R$165,80)
2. Delegates to **financial-agent** → RAG searches CDC for `produto com defeito`, returns Art. 26 (90 dias para duráveis), Art. 18 (30 dias para sanar vício), calculates full refund (R$165,80 including freight)
3. Returns humanized response with applicable rights and available actions

---

### Direct API tests

You can also call the agents directly:

```bash
# Check Mock API
curl http://localhost:8003/orders/PV-2026-00142

# Check Logistics Agent Card
curl http://localhost:8001/.well-known/agent-card.json

# Check Financial Agent Card
curl http://localhost:8002/.well-known/agent-card.json

# Check Coordinator status
curl http://localhost:8000/status

# Send a message directly to the logistics agent via A2A
curl -X POST http://localhost:8001/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "messageId": "msg-001",
        "parts": [{"kind": "text", "text": "Rastreie o pedido PV-2026-00142 com código SB123456789BR. Data prevista: 2026-05-02."}]
      }
    }
  }'
```

## Port Map

| Port | Service | Description |
|---|---|---|
| 3000 | frontend | Agent UI — browser chat interface |
| 8000 | coordinator | Agno AgentOS + AG-UI streaming endpoint |
| 8001 | logistics | PydanticAI + FastA2A JSON-RPC server |
| 8002 | financial | CrewAI + FastAPI JSON-RPC server |
| 8003 | mock-api | Mock orders REST API |

## Project Structure

```
postvenda-ai/
├── .env.example
├── docker-compose.yml
├── frontend/
│   └── Dockerfile              # Clones + builds agno-agi/agent-ui (Next.js)
├── mock-api/
│   ├── data.py                 # In-memory orders, incidents, refunds, vouchers
│   ├── main.py                 # FastAPI REST endpoints
│   └── Dockerfile
├── agents/
│   ├── logistics/              # PydanticAI A2A Server
│   │   ├── agent.py            # Agent + to_a2a() → ASGI app
│   │   └── tools.py            # track_package, calculate_delay_days, open_incident, …
│   └── financial/              # CrewAI A2A Server
│       ├── agent.py            # CrewAI Agent + FastAPI A2A endpoints
│       ├── tools.py            # @tool decorators: check_cdc_eligibility, issue_refund, …
│       └── rag/
│           ├── cdc.md          # Brazilian Consumer Defense Code content
│           ├── build_index.py  # FAISS index builder (init container)
│           └── index.py        # search_cdc() with lru_cache
└── coordinator/
    ├── agent.py                # Agno Agent + AgentOS + AGUI interface
    ├── tools.py                # fetch_order, fetch_refund_eligibility, delegate (A2A)
    └── registry.py             # Dynamic agent discovery via Agent Cards
```

## Mock Orders

| Order ID | Customer | Product | Status | Scenario |
|---|---|---|---|---|
| `PV-2026-00142` | Maria Silva | Tênis Runner Pro (R$299,90) | in_transit | Delayed SEDEX — triggers financial escalation |
| `PV-2026-00099` | João Souza | Câmera WiFi (R$189,00) | delivered | PAC delivered — test regret refund |
| `PV-2026-00210` | Ana Costa | Fone Bluetooth (R$149,90) | delivered | SEDEX delivered — test defect claim |

## A2A Protocol

Both specialized agents implement the [A2A protocol](https://google.github.io/A2A/):
- **Agent Card** at `GET /.well-known/agent-card.json` — describes capabilities
- **JSON-RPC** at `POST /` — `message/send` and `tasks/get` methods
- **PydanticAI** (FastA2A) runs tasks asynchronously — coordinator polls `tasks/get`
- **CrewAI** returns results synchronously — `message/send` responds with `completed` state

## Tech Decisions

| Decision | Reason |
|---|---|
| **Groq** for all models | Free tier, low latency, solid tool-calling support |
| **`llama-3.3-70b-versatile`** for logistics | Robust tool-calling across 6 tools with escalation logic |
| **`gpt-oss-120b`** for coordinator | Most capable Groq model for multi-agent reasoning |
| **`gpt-oss-20b`** for financial | Balance of cost/capability for structured financial tasks |
| **`lru_cache`** on RAG index | Load FAISS once per process, avoid repeated deserialization |
| **Shared volume** for RAG | `rag-builder` builds and exits; `financial` reads from same volume |
| **`escalate_financial` flag** | Logistics agent signals explicitly — coordinator doesn't need to parse numbers |
| **Polling at 1.5s interval** | Balances responsiveness vs. request count; 55s timeout |
