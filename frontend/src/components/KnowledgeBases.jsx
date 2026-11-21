import React, { useState } from "react";
import { api } from "../api.js";

export default function KnowledgeBases({ knowledgeBases, onChanged }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(e) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await api("/knowledge-bases", {
        method: "POST",
        body: { name: name.trim(), description: description.trim() },
      });
      setName("");
      setDescription("");
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(knowledgeBase) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await api(`/knowledge-bases/${knowledgeBase.id}`, { method: "DELETE" });
      await onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="knowledge-bases">
      <h2>Knowledge bases</h2>
      <p>Separate document collections by team, topic, or access boundary.</p>
      <form className="knowledge-base-form" onSubmit={create}>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Knowledge base name"
          maxLength={120}
          required
        />
        <input
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder="Description (optional)"
          maxLength={500}
        />
        <button type="submit" disabled={busy || !name.trim()}>
          Create knowledge base
        </button>
      </form>
      {error && <p className="error">{error}</p>}
      {knowledgeBases.length ? (
        <div className="knowledge-base-list">
          {knowledgeBases.map((knowledgeBase) => (
            <article key={knowledgeBase.id} className="knowledge-base-card">
              <div>
                <h3>{knowledgeBase.name}</h3>
                <p>{knowledgeBase.description || "No description"}</p>
                <small>{knowledgeBase.document_count} documents</small>
              </div>
              <button
                type="button"
                onClick={() => remove(knowledgeBase)}
                disabled={busy || knowledgeBase.document_count > 0}
                title={
                  knowledgeBase.document_count > 0
                    ? "Move or delete its documents first"
                    : "Delete knowledge base"
                }
              >
                Delete
              </button>
            </article>
          ))}
        </div>
      ) : (
        <p className="dashboard-empty">Create a knowledge base to organize documents.</p>
      )}
    </section>
  );
}
