# OpenVC-AI A2A Starter Kit

OpenVC-AI is an A2A-style multi-agent investment research platform. This completed version keeps the original stock-forecasting MVP and adds the missing A2A foundation around it: agent cards, capability discovery, a task lifecycle, task planning, local tool usage, short-term memory, and demo-mode fallbacks so the app can run without external API keys.

## What is included

- **Central A2A Orchestrator** for task planning, routing, and lifecycle tracking.
- **Agent Cards** with capabilities, skills, protocols, endpoints, and status.
- **Agent Registry / Discovery** through `/agents`, `/agents/discover`, and `/a2a/card`.
- **Task lifecycle** through `/tasks`, `/tasks/{task_id}`, and `/tasks/{task_id}/events`.
- **Tool abstraction** through `ToolPort`, `LocalToolRegistry`, `/tools`, and `/tools/execute`.
- **Planner** that builds a capability-based plan for stock-forecast tasks.
- **Persistent memory** through Postgres, SQLite, or in-memory fallback and `/memory/{session_id}`.
- **Demo mode** with synthetic price data, synthetic news, and a local mock LLM when keys are missing.
- **Real provider support** for Alpha Vantage, Finnhub, Groq, and OpenAI when keys are provided.
- **FastAPI** API with health, readiness, status, config, cache, quote, forecast, tools, tasks, and A2A endpoints.

## Architecture

```text
User / API Client
  |
FastAPI Controller
  |
AppRuntime
  |-- Agent Registry
  |-- Tool Registry
  |-- Task Store
  |-- Memory Store (Postgres / SQLite / in-memory)
  |
CentralA2AOrchestrator
  |-- CapabilityPlanner
  |-- QuantForecastAgent
  |-- NewsAnalysisAgent
  |-- InvestmentMemoAgent
  |
Ports / Adapters
  |-- LLMPort -> Groq / OpenAI / Mock Demo LLM
  |-- Market Data -> Alpha Vantage / Demo Data
  |-- News -> Finnhub / Demo News
```

The agents run locally by default, but the project now has the contracts and models needed to move individual agents behind remote A2A transports later.

## Run locally

```bash
cd openvc-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m openvc_ai.main
```

Open:

```text
http://localhost:5050/docs
```

By default, `DEMO_MODE=true`, so the API runs without external keys. To use real data and LLMs, copy `.env.example` to `.env` and add keys.

## Deploy on Vercel

This repo includes a Vercel Python service entrypoint at `api/index.py` and `vercel.json`.
For durable memory, create a hosted Postgres database such as Neon and set `DATABASE_URL`
in Vercel project environment variables.

See `DEPLOYMENT.md` for the production checklist.

## Environment

```bash
cp .env.example .env
```

Important settings:

```env
DEMO_MODE=true
DATABASE_URL=
GROQ_API_KEY=
OPENAI_API_KEY=
ALPHA_VANTAGE_API_KEY=
FINNHUB_API_KEY=
```

Set `DEMO_MODE=false` if you want missing real providers to fail instead of using local fallbacks.

## Main endpoints

### Health and status

```bash
GET /health
GET /ready
GET /status
GET /config
GET /cache/stats
```

### Agent cards and discovery

```bash
GET /a2a/card
GET /agents
GET /agents/discover?capability=price_forecast
GET /agents/by-name/QuantForecastAgent
```

### Tools

```bash
GET /tools
POST /tools/execute
```

Example tool call:

```bash
curl -X POST http://localhost:5050/tools/execute \
  -H "Content-Type: application/json" \
  -d '{"tool_name":"price_history","arguments":{"ticker":"NVDA"}}'
```

### Forecast endpoint

```bash
curl -X POST http://localhost:5050/forecast \
  -H "Content-Type: application/json" \
  -d '{"ticker":"NVDA","horizon_days":30,"include_news":true,"include_memo":true,"session_id":"demo"}'
```

### A2A task endpoint

```bash
curl -X POST http://localhost:5050/a2a/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_type":"forecast_stock",
    "session_id":"demo",
    "input":{
      "ticker":"NVDA",
      "horizon_days":30,
      "include_news":true,
      "include_memo":true,
      "session_id":"demo"
    }
  }'
```

Then inspect task state:

```bash
GET /tasks
GET /tasks/{task_id}
GET /tasks/{task_id}/events
GET /memory/demo
```

## Tests

```bash
pytest
```

## What is still intentionally local

This is now a complete **local A2A-style starter kit**, not a distributed A2A network. The next production step would be replacing selected local agents/tools with remote A2A servers using the same agent-card, task, registry, and tool contracts.

## Safety note

This project produces research-style outputs only. It is not financial advice and should not be used as an automated trading system without validation, risk controls, and compliance review.
