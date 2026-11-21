# API Reference (v1)

Base URL: `/api/v1`. Auth: `Authorization: Bearer <access_token>` unless noted.

## Auth
| Method | Path | Body | Notes |
|---|---|---|---|
| POST | /auth/register | `{email, password}` | 201 → UserOut |
| POST | /auth/login | `{email, password}` | 200 → access + refresh tokens |
| POST | /auth/refresh | `{refresh_token}` | rotates both tokens |
| GET | /auth/me | — | current user |

## Documents
| Method | Path | Body | Notes |
|---|---|---|---|
| POST | /documents/upload | multipart `file` | pdf/txt/md/html, ≤20MB. 202 → async ingestion |
| POST | /documents/text | `{title, content, metadata}` | 202 |
| GET | /documents | — | own documents w/ status |
| DELETE | /documents/{id} | — | owner or admin; removes vectors too |

Status lifecycle: `pending → processing → ready | failed(error)`.

## Search & Chat
| Method | Path | Body | Notes |
|---|---|---|---|
| POST | /search | `{query, top_k}` | raw semantic search, scored hits |
| POST | /chat | `{message, conversation_id?}` | agentic answer + citations |
| POST | /chat/stream | same | SSE: `meta`, `token`*, `done`, `error` events |
| GET | /chat/conversations | — | own conversation list |
| GET | /chat/conversations/{id} | — | full message history |

## Admin (role: admin)
| Method | Path | Notes |
|---|---|---|
| GET | /admin/usage?days=7 | cost/tokens/latency grouped by operation+model |
| GET | /admin/evals | stored eval runs |

## Health
| GET /health | liveness |
| GET /health/ready | readiness: postgres/redis/qdrant checks |

## Errors
`{"detail": "..."}` with 400 (guardrail), 401, 403, 404, 429 (+retry-after), 502 (AI provider).
Every response carries `x-request-id` for log/trace correlation.
