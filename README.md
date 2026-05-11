# PostVenda AI — Multi-Agent After-Sales Orchestrator

Sistema multi-agente para atendimento pós-venda de e-commerce brasileiro, construído com o **protocolo A2A** (Agent-to-Agent) e um **servidor MCP central** para acesso unificado aos dados de pedidos. Três agentes especializados colaboram para resolver problemas logísticos, reembolsos e dúvidas sobre direitos do consumidor — orquestrados por um coordenador LangGraph com interface de chat em tempo real.

## Arquitetura

```
Browser → http://localhost:3000          (agent-chat-ui — Next.js)
            │  LangGraph SDK (SSE streaming)
            ▼
         http://localhost:2024           (Coordinator — LangGraph)
            │                                          ▲
            │  A2A JSON-RPC ──→ http://logistics:8001  (PydanticAI)
            │  A2A REST     ──→ http://financial:8002  (Agno AgentOS)
            │                                          │
            └────────── MCP (Streamable HTTP) ─────────┤
                                ▼                      ▼
                        http://orders-mcp:8004         │
                                │                      │
                                └──→ http://mock-api:8003 (FastAPI)
```

| Serviço | Framework | Modelo (via Groq) | Porta |
|---|---|---|---|
| **Coordinator** | LangGraph (ReAct + create_agent) | `openai/gpt-oss-120b` | 2024 |
| **Logistics Agent** | PydanticAI (FastA2A) | `llama-4-scout-17b-16e-instruct` | 8001 |
| **Financial Agent** | Agno (AgentOS + A2A) | `openai/gpt-oss-20b` | 8002 |
| **Orders MCP** | FastMCP (Streamable HTTP) | — | 8004 |
| **Mock API** | FastAPI | — | 8003 |
| **Frontend** | `langchain-ai/agent-chat-ui` (Next.js) | — | 3000 |

### Por que um MCP central?

Todas as operações de leitura/escrita de pedidos vivem em **um único servidor MCP** (`orders-mcp`). Cada agente acessa apenas as tools relevantes ao seu domínio, usando o **adapter MCP nativo** do seu framework:

| Agente | Adapter | Tools MCP expostas |
|---|---|---|
| Coordinator | `langchain-mcp-adapters` (`MultiServerMCPClient`) | `fetch_order` |
| Logistics | `pydantic_ai.mcp.MCPServerStreamableHTTP` + `FilteredToolset` | `open_incident`, `update_order_status` |
| Financial | `agno.tools.mcp.MCPTools` | `fetch_order`, `fetch_refund_eligibility`, `issue_refund`, `generate_voucher` |

Isso elimina código duplicado de `httpx` em cada agente, centraliza autenticação/observabilidade no ponto de acesso aos dados, e permite que novos agentes consumam o mesmo catálogo de tools sem reimplementação.

## Quick Start

### 1. Pré-requisitos

- Docker + Docker Compose
- Chave gratuita da [Groq](https://console.groq.com)
- (opcional) Chaves do [Langfuse](https://cloud.langfuse.com) para observabilidade

### 2. Configurar

```bash
cp .env.example .env
# Edite .env com GROQ_API_KEY e (opcionalmente) chaves do Langfuse
```

### 3. Rodar

```bash
docker compose up --build
```

Abra **http://localhost:3000** para conversar com o coordenador.

> Na sidebar do agent-chat-ui, deixe `Deployment URL = http://localhost:2024` e `Assistant ID = coordinator`.

## Exemplos de uso

### Pedido atrasado — aciona logistics + escalação para financial

```
Meu pedido PV-2026-00142 devia ter chegado semana passada e até agora não chegou. O que está acontecendo?
```

**Fluxo esperado:**
1. Coordinator chama `fetch_order` (via MCP) e identifica o pedido de Maria Silva
2. Delega para **logistics-agent** (A2A JSON-RPC) → rastreia `SB123456789BR`, calcula atraso, abre incidente via `open_incident` (MCP), sinaliza `escalate_financial=true`
3. Delega para **financial-agent** (A2A REST/Agno) → verifica elegibilidade CDC, gera voucher de compensação via `generate_voucher` (MCP)
4. Retorna resposta consolidada ao cliente

### Devolução por arrependimento — direto para financial

```
Quero devolver o pedido PV-2026-00099. Comprei uma câmera mas não gostei, posso devolver?
```

**Fluxo:** coordinator → financial-agent → checagem CDC Art. 49 → `issue_refund` via MCP → resposta com ID do reembolso.

### Dúvida sobre direitos do consumidor (RAG)

```
Comprei o pedido PV-2026-00210 mas o fone veio com defeito. Quais são meus direitos?
```

**Fluxo:** coordinator → financial-agent → RAG sobre CDC (Art. 18, 26) → cálculo de reembolso integral.

### Testes diretos via API

```bash
# Mock API
curl http://localhost:8003/orders/PV-2026-00142

# MCP server (lista tools)
curl -X POST http://localhost:8004/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Logistics Agent Card (JSON-RPC A2A)
curl http://localhost:8001/.well-known/agent-card.json

# Financial Agent Card (REST A2A / Agno)
curl http://localhost:8002/a2a/agents/financial-agent/.well-known/agent-card.json

# Coordinator (LangGraph) health
curl http://localhost:2024/ok
```

## Mock Orders

| Order ID | Cliente | Produto | Status | Cenário |
|---|---|---|---|---|
| `PV-2026-00142` | Maria Silva | Tênis Runner Pro (R$325,80) | in_transit | SEDEX atrasado → escalação financeira |
| `PV-2026-00099` | João Souza | Câmera WiFi (R$189,00) | delivered | PAC entregue → arrependimento CDC Art. 49 |
| `PV-2026-00210` | Ana Costa | Fone Bluetooth (R$149,90) | delivered | SEDEX entregue → defeito CDC Art. 18/26 |

## Protocolos A2A

Os dois agentes especializados implementam variações do [protocolo A2A](https://google.github.io/A2A/):

| Agente | Estilo | Endpoint | Wire format |
|---|---|---|---|
| **Logistics** (PydanticAI/FastA2A) | JSON-RPC | `POST /` | `message/send` + polling de `tasks/get` |
| **Financial** (Agno) | REST (com payload JSON-RPC) | `POST /a2a/agents/financial-agent/v1/message:send` | Body `{id, params: {message}}`, resposta síncrona |

O coordinator detecta o protocolo via campo `protocol` no `AGENT_REGISTRY` (`coordinator/registry.py`) e roteia adequadamente em `coordinator/tools.py:delegate`.

## Estrutura do projeto

```
postvenda-ai/
├── .env.example
├── docker-compose.yml
├── frontend/
│   └── Dockerfile             # Clona + builda langchain-ai/agent-chat-ui
├── mock-api/                  # FastAPI — fonte da verdade dos pedidos
│   ├── data.py                # ORDERS, INCIDENTS, REFUNDS, VOUCHERS em memória
│   ├── main.py                # Endpoints REST
│   └── Dockerfile
├── orders-mcp/                # FastMCP — gateway único para mock-api
│   ├── server.py              # 6 tools: fetch_order, fetch_refund_eligibility,
│   │                          # open_incident, update_order_status,
│   │                          # issue_refund, generate_voucher
│   └── Dockerfile
├── logistics/                 # PydanticAI A2A Server (port 8001)
│   ├── agent.py               # Agent + FilteredToolset(MCPServerStreamableHTTP)
│   ├── tools.py               # track_package, quote_reverse_shipping,
│   │                          # validate_address, calculate_delay_days
│   └── Dockerfile
├── financial/                 # Agno AgentOS A2A Server (port 8002)
│   ├── agent.py               # Agent + MCPTools + AgentOS(a2a_interface=True)
│   ├── tools.py               # check_cdc_eligibility, calculate_refund_amount,
│   │                          # get_consumer_rights (RAG)
│   ├── rag/                   # FAISS index sobre cdc.md
│   └── Dockerfile
└── coordinator/               # LangGraph ReAct Agent (port 2024)
    ├── graph.py               # create_agent + MultiServerMCPClient + Langfuse
    ├── tools.py               # delegate (A2A roteado por protocolo)
    ├── registry.py            # Discovery dinâmico via Agent Cards
    ├── langgraph.json         # Manifesto do LangGraph Server
    └── Dockerfile
```

## Observabilidade

Todos os três agentes emitem traces para o **Langfuse** quando `LANGFUSE_PUBLIC_KEY` e `LANGFUSE_SECRET_KEY` estão definidos:

- **Coordinator** → `langfuse.langchain.CallbackHandler` injetado via `.with_config({"callbacks": [...]})`
- **Logistics** → `PydanticAgent.instrument_all()` + `instrument=True`
- **Financial** → OpenTelemetry + `AgnoInstrumentor` exportando OTLP/HTTP para o endpoint Langfuse

Os traces aparecem em **https://cloud.langfuse.com** sob o projeto correspondente à chave.

## Decisões técnicas

| Decisão | Motivo |
|---|---|
| **MCP central (orders-mcp)** | Elimina httpx duplicado, centraliza acesso aos dados, permite onboarding de novos agentes sem mudar mock-api |
| **Adapters MCP nativos** | `langchain-mcp-adapters` no coord, `MCPServerStreamableHTTP` no PydanticAI, `MCPTools` no Agno — cada framework usa sua API idiomática |
| **Filtragem por nome** | Cada agente recebe só as tools relevantes ao seu domínio (princípio de menor privilégio) |
| **LangGraph para o coord** | `create_agent` (ReAct) + suporte nativo a SSE streaming via LangGraph Server, integração direta com agent-chat-ui |
| **Discovery via Agent Cards** | Routing rules vivem no campo `description` do card de cada agente — coordinator é agnóstico ao domínio |
| **Agno para o financial** | `AgentOS(a2a_interface=True)` gera endpoints A2A automáticos; bom suporte a RAG via Knowledge |
| **PydanticAI para o logistics** | Tool calling tipado + FastA2A nativo + `FilteredToolset` para restringir MCP |
| **Groq para todos os modelos** | Free tier, baixa latência, bom suporte a tool calling |
