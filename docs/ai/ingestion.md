# Document ingestion

## What and why

Ingestion converts source files into text that the retrieval pipeline can chunk, embed,
and search. Parsing and indexing are separate concerns: the upload API validates and
extracts content, then a background worker performs chunking and embedding so vector work
does not occupy the chat request path.

## Flow

```text
upload API
  → validate media type and byte limit
  → extract text + parser metadata (PDF, DOCX, HTML, or plain text)
  → hash extracted UTF-8 content
  → return existing same-owner document if hash already exists
  → persist pending document, commit, enqueue worker job
  → worker chunks → embeds → indexes → marks ready or failed
```

DOCX extraction includes paragraphs, tables, and core properties. PDF extraction includes
page count and available title/author metadata. The content hash is unique per owner;
identical extracted content from that owner's uploads or text-ingest requests returns the
existing document and does not enqueue a second job. A database uniqueness constraint
handles concurrent duplicate submissions. Different owners can independently ingest the
same content.

## Implementation and data flow

- `backend/app/services/document_service.py` validates input, extracts text and metadata,
  computes a SHA-256 digest, and enqueues the existing arq job.
- `backend/app/db/models.py` stores the digest and enforces per-owner uniqueness.
- `backend/app/db/repositories/documents.py` owns hash lookup and document creation.
- `database/migrations/versions/0002_document_content_hash.py` adds the nullable digest
  column and uniqueness constraint without rewriting the initial migration.
- `backend/app/workers/worker.py` continues to process pending content asynchronously.
- `frontend/src/components/Documents.jsx` advertises DOCX upload support.

The digest is based on extracted text rather than raw file bytes. Reformatting a document
without changing its extracted text therefore avoids duplicate indexing. The trade-off is
that extraction differences between parser versions can change the hash.

## Run and verify

Run the app using the [Windows PowerShell setup](../../README.md#windows-powershell), apply
the database migration, and upload a PDF, DOCX, TXT, Markdown, or HTML file. The document
status moves through the worker's processing lifecycle. Uploading the same extracted
content again for the same account returns the existing document.

Focused checks:

```powershell
python -m pytest -q tests\test_ingestion.py
```

## Failure modes

- Unsupported media type returns HTTP 415; oversize files return HTTP 413.
- Empty or unextractable documents are rejected rather than queued as successful work.
- Worker failures remain visible on the document's `failed` status and error field.
- If enqueueing fails after the row is committed, the document can remain pending; this
  should be monitored and retried operationally.

## Interview questions

1. **Why hash extracted text instead of the original file?** It makes identical content
   idempotent across file names and formats. It does mean parser-version changes can alter
   the digest, so parser versions may need to be recorded for long-lived systems.
2. **Why use a database uniqueness constraint in addition to a pre-check?** The pre-check
   is fast, but concurrent requests can both miss. The unique constraint is the final
   consistency boundary.
3. **Why commit before enqueueing?** The worker needs to see the document row when it
   starts. A stronger transactional outbox would close the crash window between commit and
   queue submission.
4. **What does the content hash not guarantee?** It is an exact-content deduplicator, not
   semantic duplicate detection or malware validation.

## Exercise

Implement a transactional outbox for ingestion jobs and add a worker that retries
committed-but-not-enqueued documents without duplicating indexed chunks.
