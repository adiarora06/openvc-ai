# Deployment Guide

## Target Architecture

- Vercel hosts the FastAPI app as a Python service.
- Neon or another hosted Postgres provider stores persistent memory records.
- Groq or OpenAI powers memo/news generation.
- Alpha Vantage and Finnhub provide real market/news data when `DEMO_MODE=false`.

## Vercel Setup

1. Create a Vercel project from this repository.
2. Set the Framework Preset to `Services`.
3. Keep `vercel.json` at the repository root.
4. Deploy a preview build.
5. Open `/health`, `/docs`, and `/memory/stats` on the preview URL.

The Vercel entrypoint is `api/index.py`, which imports the FastAPI `app` from
`openvc_ai.api.app`.

## Database Setup

Create a Postgres database using Neon, Supabase, Railway, Render, or another
hosted provider. For Vercel, Neon through the Vercel Marketplace is the smoothest
default because it can inject environment variables into the project.

Set this environment variable in Vercel:

```env
DATABASE_URL=postgresql://...
```

Use a pooled connection string when your provider offers one. On startup, the
app creates this table automatically:

```sql
CREATE TABLE IF NOT EXISTS memory_records (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    kind        TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL,
    tier        TEXT NOT NULL DEFAULT 'short'
);
```

If `DATABASE_URL` is not set or Postgres is unavailable, the app falls back to
SQLite locally and then in-memory storage if SQLite is unavailable.

## Production Environment Variables

```env
DEMO_MODE=false
DATABASE_URL=

PRIMARY_LLM_PROVIDER=groq
GROQ_API_KEY=
GROQ_MODEL=llama-3.3-70b-versatile
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini

ALPHA_VANTAGE_API_KEY=
FINNHUB_API_KEY=

LOG_LEVEL=INFO
REQUEST_TIMEOUT_SECONDS=30
CACHE_TTL_SECONDS=300
MONTE_CARLO_SIMULATIONS=2000
SAMPLE_PATHS=20
```

Use `DEMO_MODE=true` for previews if you want the app to keep working before
all provider keys are configured.

## Local Verification

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python -m openvc_ai.main
```

Open:

```text
http://localhost:5050
http://localhost:5050/docs
```

## Full Application Roadmap

1. Add authentication so users have private workspaces and saved research.
2. Persist A2A tasks and forecast runs, not only memory records.
3. Add database migrations with Alembic before the schema grows.
4. Add a real frontend app, likely Next.js, once the static UI needs auth,
   dashboards, saved reports, billing, or richer client-side state.
5. Add rate limiting and per-user quotas before exposing expensive LLM/provider
   calls publicly.
6. Add observability for API latency, provider failures, and forecast costs.
