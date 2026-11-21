# Knowledge base isolation

## Purpose

Knowledge bases organize a user's documents into explicit retrieval scopes. In this
implementation, each knowledge base belongs to one user; sharing and team-level ACLs
are intentionally not implied. A user can select a knowledge base for uploads and chats,
or search all of their documents.

## Data model

```text
User 1 ─── * KnowledgeBase 1 ─── * Document 1 ─── * DocumentChunk
  └────────────────────────────── * Document
```

Documents may have no knowledge base for compatibility with existing uploads. A document
inside a knowledge base must still have the same owner. Content hashes are unique within
an owner's knowledge base, allowing the same extracted content to be independently
indexed in separate collections. `0003_knowledge_bases` adds the ownership model and
document membership; `0004_conversation_knowledge_base` records a chat's selected scope.

## Request flow

1. The frontend loads the signed-in user's knowledge bases and selects one in the
   workspace filter.
2. Upload and text-ingestion requests include its ID. The service verifies ownership
   before storing or enqueueing a document.
3. The worker stores owner and knowledge-base IDs in every Qdrant point.
4. The conversation stores the selected knowledge base. Follow-up turns reuse that
   scope; a client cannot switch an existing conversation to a different knowledge base.
5. LangGraph injects the authenticated owner and conversation scope into the retrieval
   tool. They are not model-generated arguments.
6. Qdrant and PostgreSQL BM25 both filter on owner and, when selected, knowledge base.
7. Moving a ready document checks destination ownership and content-hash uniqueness,
   updates its Qdrant scope payload, and commits the matching PostgreSQL membership.

## Deletion and migration

A knowledge base can be deleted only when it has no documents. This avoids silently
moving indexed content or destroying user data. Ready documents can be moved through the
Documents page or `PATCH /documents/{id}/knowledge-base`; the operation checks destination
ownership and duplicate content, then updates PostgreSQL membership and Qdrant payload
scope. Documents in ingestion must finish first. Apply Alembic migrations through
`0004_conversation_knowledge_base` before running the new API.
For existing Qdrant points, run `python scripts/backfill_vector_owners.py` after migrations;
the backfill also adds each point's current knowledge-base ID.

## Limits and next step

This is owner isolation, not a group-sharing ACL system. A future team workspace should
model membership and roles explicitly and enforce authorization in both relational and
vector retrieval. Do not treat possession of a knowledge-base UUID as permission.

## Interview questions

1. **Why pass the owner ID through injected graph state?** The model chooses a search
   query, but the authenticated application—not the model—chooses whose data it can see.
2. **Why persist the knowledge-base ID on the conversation?** Follow-up questions need a
   stable retrieval scope and must not silently switch data boundaries when UI selection
   changes.
3. **Why restrict knowledge-base deletion when populated?** It prevents accidental
   orphaning or silent movement of documents; an explicit move/delete workflow is safer.
4. **How would you add shared team knowledge?** Add memberships/roles and apply
   authorized collection filters in both SQL and Qdrant, with tests for revocation and
   concurrent membership changes.
5. **How do you keep PostgreSQL membership and Qdrant payload scope aligned during a move?**
   Validate ownership and duplicate content before changing either store, update vector
   metadata within the request, and restore the old vector scope if the relational commit
   fails. For stronger crash consistency at scale, use a transactional outbox and reconcile
   pending scope updates asynchronously.
