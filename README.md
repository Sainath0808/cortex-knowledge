# Cortex — Enterprise Knowledge Copilot

A document Q&A application where users ingest documents and ask questions through a
tool-using LLM agent. Cortex combines retrieval-augmented generation (RAG), guardrails,
evaluation, and request tracing.

**Goal:** make organization-specific documents searchable and provide cited answers. Cortex
organizes documents into user-owned knowledge bases, processes ingestion asynchronously, and
tracks provider usage and failures.

## Architecture

```
                         ┌────────────┐
   React SPA ──HTTP────► │  FastAPI   │──► Auth (JWT + RBAC)
                         │   API      │──► Rate limit (Redis sliding window)
                         └─────┬──────┘──► Guardrails (injection / PII / moderation)
                               │
              ┌────────────────┼─────────────────────┐
              ▼                ▼                     ▼
        ┌──────────┐   ┌────────────────┐    ┌──────────────┐
        │ Postgres │   │ LangGraph Agent│    │  arq Worker  │
        │ (system  │   │ guard→agent⇄tools    │ (ingestion:  │
        │ of record)│  └───────┬────────┘    │ chunk→embed→ │
        └──────────┘           │             │ index)       │
                               ▼             └──────┬───────┘
                      ┌─────────────────┐           │
                      │  RAG pipeline   │◄──────────┘
                      │ retrieve→rerank │
                      │ →context→answer │
                      └───┬─────────┬───┘
                          ▼         ▼
                     ┌────────┐ ┌──────────────┐
                     │ Qdrant │ │ Azure OpenAI │
                     │(vectors)│ │ (chat+embed) │
                     └────────┘ └──────────────┘

  MCP server (mcp_server/) exposes knowledge_search to any MCP client.
  OpenTelemetry traces the full chain; costs land in the llm_usage table.
```

## Repository structure

```
backend/app/        FastAPI app: api routes, services, db, middleware, workers
ai/                 AI layer: llm client, prompts, RAG, guardrails, evals
agents/             LangGraph agent: state, graph, tools, memory
mcp_server/         MCP server exposing the knowledge base as standard tools
database/           Alembic migrations
frontend/           React SPA (Vite)
tests/              pytest suite (no live LLM calls)
scripts/            seed + sample-document ingestion
deployment/         Dockerfiles, Kubernetes manifests
docs/               architecture docs + ADRs + AI design docs
.github/workflows/  CI: lint, test, build+push images
```

## Quickstart

```bash
# 1. Infrastructure
cp .env.example .env          # fill in Azure OpenAI values
docker compose up -d postgres redis qdrant

# 2. Python env (3.11+)
pip install -e ".[dev]"

# 3. Database
# (Windows PowerShell: $env:PYTHONPATH="backend;.")
export PYTHONPATH=backend:.
alembic upgrade head
python scripts/seed.py

# 4. Run
uvicorn app.main:app --reload            # API  -> http://localhost:8000/docs
arq app.workers.worker.WorkerSettings    # worker (second terminal)
cd frontend && npm install && npm run dev  # UI -> http://localhost:5173

# 5. Sample data + smoke test
python scripts/ingest_sample_docs.py
```

### Windows PowerShell

Use Python 3.11 or newer (the project is tested with Python 3.12), Node.js, and Docker
Desktop. Run these commands from the repository root:

```powershell
Copy-Item .env.example .env
# Edit .env and configure the LLM provider before asking questions.
docker compose up -d postgres redis qdrant

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:PYTHONPATH = "backend;."
alembic upgrade head
python scripts/seed.py
```

In separate PowerShell terminals, activate the same virtual environment and set
`$env:PYTHONPATH = "backend;."`, then run:

```powershell
uvicorn app.main:app --reload
```

```powershell
arq app.workers.worker.WorkerSettings
```

```powershell
Set-Location frontend
npm install
npm run dev
```

The UI runs at `http://localhost:5173`; the API docs are at `http://localhost:8000/docs`.
If `py -3.12` is unavailable, install Python 3.12 or use an installed supported version
by replacing `3.12` in the virtual-environment command.

Demo logins: `admin@cortex.local` / `admin-password-123`, `demo@cortex.local` / `demo-password-123`.

## Local LLM with Ollama (no cloud key needed)

```bash
docker compose --profile ollama up -d ollama
docker exec -it $(docker compose ps -q ollama) ollama pull llama3.1
docker exec -it $(docker compose ps -q ollama) ollama pull nomic-embed-text
```

Then in `.env`:

```
LLM_PROVIDER=openai
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_CHAT_MODEL=llama3.1
LLM_EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
```

Changing the embedding model changes vector dimensions — delete the Qdrant collection
(`curl -X DELETE localhost:6333/collections/cortex_chunks`), restart the API (it recreates
the collection at the new size), and re-ingest documents.

Retrieval is restricted to the authenticated user's documents. For an existing Qdrant
collection created before owner metadata was added, run
`python scripts/backfill_vector_owners.py` once after applying migrations and starting
PostgreSQL and Qdrant. MCP and evaluation commands also require `MCP_OWNER_ID` and
`EVAL_OWNER_ID` to identify their explicitly scoped service accounts.

## Example API requests

```bash
# Login
curl -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"demo@cortex.local","password":"demo-password-123"}'

# Ingest text (async — worker embeds and indexes it)
curl -X POST localhost:8000/api/v1/documents/text \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"title":"Test Policy","content":"Employees may expense up to $50 for books."}'

# Agentic chat with citations
curl -X POST localhost:8000/api/v1/chat \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"message":"What can I expense for books?"}'

# Raw semantic search
curl -X POST localhost:8000/api/v1/search \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"query":"book expenses","top_k":3}'

# Admin: cost/usage dashboard
curl localhost:8000/api/v1/admin/usage -H "Authorization: Bearer $ADMIN_TOKEN"
```

## Testing & evals

```bash
pytest -q                          # unit + API tests (LLM faked, SQLite in-memory)
python -m ai.evals.run_evals       # retrieval metrics + LLM-judge faithfulness
```

Before running evaluations, set `EVAL_OWNER_ID` in `.env` to the UUID of the account
holding the evaluation corpus. The evaluator does not search across users.

## MCP server

```bash
python -m mcp_server.server        # stdio transport
```
Register in any MCP client (Claude Desktop, VS Code) to expose `knowledge_search`
and `list_documents` tools backed by the same retrieval pipeline. Set `MCP_OWNER_ID` in
`.env` to the UUID of the service account whose documents the MCP server may access.

## Deployment

- `docker compose up --build` — full local stack.
- `kubectl apply -f deployment/kubernetes/` — K8s: API (2 replicas + HPA), worker,
  datastores, ingress. Create `cortex-secrets` first (see `01-secrets.example.yaml`).
- CI (GitHub Actions): ruff + pytest + frontend build; on `main`, builds and pushes images.

## Key design docs

- [docs/architecture/overview.md](docs/architecture/overview.md) — system + data flow
- [docs/architecture/implementation-roadmap.md](docs/architecture/implementation-roadmap.md) — architecture decisions, invariants, and phased delivery
- [docs/architecture/knowledge-bases.md](docs/architecture/knowledge-bases.md) — user-owned collections and retrieval isolation
- [docs/interview-guide.md](docs/interview-guide.md) — project walkthrough, interview answers, demo flow, and design trade-offs
- [docs/ai/streaming.md](docs/ai/streaming.md) — real token streaming, moderation, and SSE flow
- [docs/ai/ingestion.md](docs/ai/ingestion.md) — PDF/DOCX extraction, metadata, deduplication, and worker flow
- [docs/ai/chunking-strategies.md](docs/ai/chunking-strategies.md) — fixed, recursive, semantic, and structure-aware chunking
- [docs/ai/hybrid-search.md](docs/ai/hybrid-search.md) — BM25 + vector fusion and owner-scoped retrieval
- [docs/adr/](docs/adr/) — architecture decision records
- [docs/ai/rag-design.md](docs/ai/rag-design.md) — chunking/retrieval/reranking choices
- [docs/ai/agents.md](docs/ai/agents.md) — agent graph and tool design
- [docs/ai/security.md](docs/ai/security.md) — threat model and guardrails
- [docs/ai/evals.md](docs/ai/evals.md) — evaluation strategy

## Troubleshooting

| Symptom | Fix |
|---|---|
| `documents` stuck in `pending` | Worker not running: `arq app.workers.worker.WorkerSettings` |
| 401 on every request | Token expired — the frontend auto-refreshes; for curl, re-login |
| 502 `AI provider is unavailable` | Azure OpenAI endpoint/key wrong, or deployment names mismatch |
| Qdrant `collection not found` | API creates it at startup — restart API after Qdrant is up |
| 429 responses | Rate limiter: 60 req/min per identity (tune in `.env`) |

## Future improvements

- Query rewriting and contextual compression
- Postgres checkpointer for LangGraph (durable multi-step agent state)
- Human-in-the-loop approval node for destructive tools
- Fine-grained document ACLs beyond per-owner isolation
