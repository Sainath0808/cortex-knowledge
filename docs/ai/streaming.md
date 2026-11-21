# Streaming agent responses

## What and why

Streaming sends generated text as it becomes available instead of making the browser wait
for an entire answer. It improves perceived latency, but it does not make model generation
faster, and it introduces concerns around partial failures, persistence, moderation, and
tool calls.

## Flow

```text
React stream reader
  ← SSE meta / token / reset / done / error
FastAPI /chat/stream
  ← ChatService.stream
LangGraph astream (messages + values)
  ← agent node iterates the provider's streaming API
  → tools run between model generations
  → final state is moderated and persisted with citations
```

The agent node aggregates model chunks into an `AIMessage` so LangGraph can still route
tool calls. The graph's message stream is independently consumed by `ChatService.stream`,
which forwards only text emitted by the agent node. Tool arguments and tool results are
not sent as answer tokens. `meta` establishes the conversation ID; `done` carries source
citations; `error` reports a safe user-facing failure.

## Moderation and failure handling

Output moderation runs before the non-streaming response is returned. For streaming,
`StreamingOutputModerator` holds back a lookahead window long enough to match each
configured literal leak marker before releasing the text. If it detects a marker, the UI
receives a `reset` event with the safe replacement. The completed graph answer is also
checked before persistence. Expand the streaming guard whenever new output policies are
added; do not assume post-hoc moderation can retract content already delivered.

Provider and graph failures are surfaced as an SSE `error` event. Internal exception text
is logged server-side but is not returned to the browser. A stream can fail after partial
text has been shown; clients should retain that partial response and display the error.

## Key implementation points

- `agents/graph.py`: enables model streaming and aggregates chunks for normal graph state
  transitions and tool routing.
- `backend/app/services/chat_service.py`: prepares the authorized conversation, forwards
  graph tokens, moderates, persists the final answer, and sends citations.
- `backend/app/api/v1/chat.py`: maps service events to SSE and hides unexpected exception
  details from clients.
- `frontend/src/api.js`: refreshes authentication and parses SSE frames from a fetch body.
- `frontend/src/components/Chat.jsx`: appends tokens to the active assistant message and
  handles reset, citation, and error events.

## Run and verify

Start the API and frontend using the [Windows PowerShell setup](../../README.md#windows-powershell),
configure a real LLM provider in `.env`, sign in, and send a prompt. The assistant message
should appear incrementally; citations appear when generation completes. The implementation
does not substitute canned text when the provider is unavailable.

Focused checks:

```powershell
python -m pytest -q tests\test_agent.py tests\test_guardrails.py
Set-Location frontend
npm run build
```

## Interview questions

1. **Why use SSE rather than WebSockets here?** Chat output is server-to-client after one
   request; SSE uses a standard HTTP response and fits this one-way event stream. WebSockets
   are more useful when both sides need frequent, long-lived messages.
2. **How does streaming interact with tool calls?** Tool-call chunks are accumulated into
   a complete message for graph routing. The UI receives answer text, not tool arguments or
   raw tool output.
3. **Why is moderation harder with streaming?** Once text reaches a client it cannot be
   recalled. A streaming filter must inspect enough buffered text to detect configured
   markers before releasing it, while final validation remains necessary.
4. **What happens when the provider fails mid-stream?** The server emits a safe error
   event and logs the internal failure. The browser keeps any already received text and
   informs the user the response was incomplete.

## Exercise

Add cancellation support to the UI: when a user cancels a response, abort the fetch,
stop the active model generation where supported, and ensure the partial answer is not
mistaken for a completed turn.
