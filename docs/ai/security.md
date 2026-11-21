# AI Security & Guardrails

## Threat model
| Threat | Vector | Defense |
|---|---|---|
| Direct prompt injection | user message | heuristics (regex) + LLM classifier, blocked with 400 |
| Indirect injection | malicious content inside ingested docs | system prompts declare retrieved text as data; output moderation |
| System prompt exfiltration | "repeat your instructions" | heuristics + output leak markers |
| PII leakage to provider/logs | user pastes SSN/emails | regex redaction before logging/LLM |
| Tool abuse / code exec | calculator input | AST evaluator, no eval(), whitelisted ops |
| Agent runaway cost | looping tool calls | hard tool budget (6) + per-call cost records |
| Credential theft | config | secrets only via env/K8s secrets; never logged |
| Cross-user data access | IDOR or cross-tenant retrieval | ownership checks in services; owner_id filters in PostgreSQL BM25 and Qdrant |
| Brute force / abuse | API flooding | Redis sliding-window rate limit per identity |

## Layered input pipeline (ChatService)
1. `heuristic_check` — zero-latency regex patterns for known jailbreaks.
2. `classify_injection` — LLM JSON classifier for subtle attacks (fails open by design here;
   flip to fail-closed for high-risk domains — one-line change, documented trade-off).
3. PII redaction (`ai/guardrails/pii.py`) before logging or upstream calls.
4. Output moderation (`ai/guardrails/moderation.py`) — leak markers scrubbed pre-response.

## Why no single layer suffices
Regexes are trivially bypassed by paraphrase; LLM classifiers have false negatives; prompt
rules can be overridden by strong attacks. Layering raises attacker cost and gives observable
signals (every block is logged with layer + reason).

## Auth design
- JWT access (30 min) + refresh (7 days), typed tokens (refresh can't hit APIs).
- bcrypt password hashing; identical error for wrong-email vs wrong-password.
- RBAC: admin/member/viewer via `require_role` dependency; admin endpoints isolated.

## Known limitations (deliberate, documented)
- Regex PII misses free-text names/addresses (NER model = future work).
- No token revocation list (JWT stateless trade-off; short expiry mitigates).
- MCP stdio server assumes trusted local invocation.
- MCP and evaluation retrieval require explicit `MCP_OWNER_ID` / `EVAL_OWNER_ID` service
  scopes; never configure them with a user-controlled request value.
- Existing Qdrant points need their owner payload backfilled before owner-filtered search
  can find them (`python scripts/backfill_vector_owners.py`).
