import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";
import { api, streamChat } from "../api.js";
import "highlight.js/styles/github-dark.css";

export default function Chat({ knowledgeBaseId, onKnowledgeBaseChange }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [historyError, setHistoryError] = useState("");
  const conversationId = useRef(null);

  async function loadConversations() {
    try {
      setConversations(await api("/chat/conversations"));
      setHistoryError("");
    } catch (err) {
      setHistoryError(err.message);
    }
  }

  useEffect(() => {
    loadConversations();
  }, []);

  async function openConversation(id) {
    if (busy) return;
    try {
      const conversation = await api(`/chat/conversations/${id}`);
      conversationId.current = conversation.id;
      onKnowledgeBaseChange(conversation.knowledge_base_id || "");
      setMessages(
        conversation.messages.map((message, index) => ({
          id: `${conversation.id}-${index}`,
          ...message,
        })),
      );
    } catch (err) {
      setHistoryError(err.message);
    }
  }

  function newConversation() {
    if (busy) return;
    conversationId.current = null;
    setMessages([]);
  }

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    const assistantId = crypto.randomUUID();
    setMessages((m) => [
      ...m,
      { role: "user", content: text },
      { id: assistantId, role: "assistant", content: "", citations: [] },
    ]);
    setBusy(true);
    try {
      await streamChat(
        {
          message: text,
          conversation_id: conversationId.current,
          knowledge_base_id: knowledgeBaseId,
        },
        (event, data) => {
          if (event === "meta") {
            conversationId.current = JSON.parse(data).conversation_id;
          } else if (event === "token") {
            setMessages((messages) =>
              messages.map((message) =>
                message.id === assistantId
                  ? { ...message, content: message.content + data }
                  : message,
              ),
            );
          } else if (event === "reset") {
            setMessages((messages) =>
              messages.map((message) =>
                message.id === assistantId ? { ...message, content: data } : message,
              ),
            );
          } else if (event === "done") {
            const result = JSON.parse(data);
            setMessages((messages) =>
              messages.map((message) =>
                message.id === assistantId
                  ? { ...message, citations: result.citations }
                  : message,
              ),
            );
          } else if (event === "error") {
            const result = JSON.parse(data);
            throw new Error(result.detail || "Chat stream failed.");
          }
        },
      );
      await loadConversations();
    } catch (err) {
      setMessages((m) => [...m, { role: "error", content: err.message }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat-layout">
      <aside className="conversation-sidebar">
        <button type="button" onClick={newConversation} disabled={busy}>
          New chat
        </button>
        {historyError && <div className="error">{historyError}</div>}
        <div className="conversation-list">
          {conversations.map((conversation) => (
            <button
              type="button"
              key={conversation.id}
              className={conversation.id === conversationId.current ? "selected" : ""}
              onClick={() => openConversation(conversation.id)}
              disabled={busy}
            >
              {conversation.title || "New conversation"}
            </button>
          ))}
        </div>
      </aside>
      <div className="chat">
        <div className="messages">
        {messages.length === 0 && (
          <div className="hint">Ask anything about your ingested documents.</div>
        )}
        {messages.map((msg, i) => (
          <div key={msg.id ?? i} className={`msg ${msg.role}`}>
            <div className="bubble">
              {msg.role === "assistant" ? (
                msg.content ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
                    {msg.content}
                  </ReactMarkdown>
                ) : busy ? (
                  "Thinking…"
                ) : null
              ) : (
                msg.content
              )}
            </div>
            {msg.citations?.length > 0 && (
              <div className="citations">
                {msg.citations.map((c, j) => (
                  <span key={j} title={c.snippet}>
                    📄 {c.document_title}
                  </span>
                ))}
              </div>
            )}
            {msg.role === "assistant" && msg.content && !busy && (
              <button
                type="button"
                className="copy-answer"
                onClick={() => navigator.clipboard.writeText(msg.content)}
                aria-label="Copy answer"
              >
                Copy
              </button>
            )}
          </div>
        ))}
        </div>
        <form onSubmit={send}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask Cortex…"
            disabled={busy}
          />
          <button type="submit" disabled={busy}>Send</button>
        </form>
      </div>
    </div>
  );
}
