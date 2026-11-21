import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/settings")
      .then(setSettings)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="error settings-error">{error}</p>;
  if (!settings) return <p className="settings-loading">Loading runtime configuration…</p>;

  return (
    <section className="settings-page">
      <h2>Settings</h2>
      <p>Effective model and retrieval configuration loaded from the API.</p>
      <article className="settings-card">
        <h3>LLM provider</h3>
        <dl>
          <div><dt>Provider</dt><dd>{settings.provider}</dd></div>
          <div><dt>Chat model / deployment</dt><dd>{settings.chat_model}</dd></div>
          <div><dt>Embedding model / deployment</dt><dd>{settings.embedding_model}</dd></div>
          <div><dt>Endpoint host</dt><dd>{settings.endpoint_host || "Not configured"}</dd></div>
          <div>
            <dt>Credentials</dt>
            <dd className={settings.credentials_configured ? "status-ready" : "status-failed"}>
              {settings.credentials_configured ? "Configured" : "Missing"}
            </dd>
          </div>
          <div><dt>Embedding dimensions</dt><dd>{settings.embedding_dimensions}</dd></div>
        </dl>
      </article>
      <article className="settings-card">
        <h3>Generation</h3>
        <dl>
          <div><dt>Temperature</dt><dd>{settings.generation.temperature}</dd></div>
          <div><dt>Maximum completion tokens</dt><dd>{settings.generation.max_completion_tokens}</dd></div>
          <div><dt>Request timeout</dt><dd>{settings.generation.timeout_seconds}s</dd></div>
          <div><dt>Retry attempts</dt><dd>{settings.generation.max_retries}</dd></div>
        </dl>
      </article>
      <article className="settings-card">
        <h3>Retrieval and ingestion</h3>
        <dl>
          <div><dt>Chunking strategy</dt><dd>{settings.retrieval.chunking_strategy}</dd></div>
          <div><dt>Chunk size</dt><dd>{settings.retrieval.chunk_size_tokens} tokens</dd></div>
          <div><dt>Chunk overlap</dt><dd>{settings.retrieval.chunk_overlap_tokens} tokens</dd></div>
          <div><dt>Candidate retrieval</dt><dd>{settings.retrieval.top_k}</dd></div>
          <div><dt>Reranked context chunks</dt><dd>{settings.retrieval.rerank_top_k}</dd></div>
          <div><dt>Maximum context</dt><dd>{settings.retrieval.max_context_tokens} tokens</dd></div>
          <div>
            <dt>Follow-up query rewriting</dt>
            <dd>{settings.retrieval.query_rewriting_enabled ? "Enabled" : "Disabled"}</dd>
          </div>
        </dl>
      </article>
      <p className="settings-note">
        These values are managed through environment configuration. Update <code>.env</code>
        and restart the API and worker to apply changes. Credentials are never returned by
        this endpoint.
      </p>
    </section>
  );
}
