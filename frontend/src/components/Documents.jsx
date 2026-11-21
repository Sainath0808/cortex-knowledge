import React, { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Documents({
  knowledgeBaseId,
  knowledgeBases = [],
  onKnowledgeBasesChanged,
}) {
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyDocumentId, setBusyDocumentId] = useState("");

  async function load() {
    try {
      const query = knowledgeBaseId
        ? `?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}`
        : "";
      setDocs(await api(`/documents${query}`));
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    load();
    const timer = setInterval(load, 5000); // poll ingestion status
    return () => clearInterval(timer);
  }, [knowledgeBaseId]);

  async function upload(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    try {
      setError("");
      const query = knowledgeBaseId
        ? `?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}`
        : "";
      await api(`/documents/upload${query}`, { method: "POST", body: form, isForm: true });
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      e.target.value = "";
    }
  }

  async function remove(id) {
    setError("");
    setNotice("");
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function reindex(id) {
    try {
      setError("");
      setNotice("");
      await api(`/documents/${id}/reindex`, { method: "POST" });
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function move(id, value) {
    const targetKnowledgeBaseId = value || null;
    setBusyDocumentId(id);
    setError("");
    setNotice("");
    try {
      await api(`/documents/${id}/knowledge-base`, {
        method: "PATCH",
        body: { knowledge_base_id: targetKnowledgeBaseId },
      });
      setNotice("Document moved. Its search scope is updated.");
      await load();
      try {
        await onKnowledgeBasesChanged?.();
      } catch (err) {
        setError(`Document moved, but knowledge-base counts could not refresh: ${err.message}`);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyDocumentId("");
    }
  }

  return (
    <div className="documents">
      <label className="upload">
        Upload document to {knowledgeBaseId ? "selected knowledge base" : "all my documents"}
        (pdf / docx / txt / md / html)
        <input type="file" onChange={upload} accept=".pdf,.docx,.txt,.md,.html" />
      </label>
      {error && <div className="error">{error}</div>}
      {notice && <div className="document-notice">{notice}</div>}
      <table>
        <thead>
          <tr>
            <th>Title</th>
            <th>Status</th>
            <th>Chunks</th>
            <th>Knowledge base</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.id}>
              <td>{d.title}</td>
              <td>
                <span className={`status ${d.status}`}>{d.status}</span>
                {d.error && (
                  <div className="document-error" title={d.error}>
                    {d.error}
                  </div>
                )}
              </td>
              <td>{d.chunk_count}</td>
              <td>
                <select
                  className="document-move"
                  aria-label={`Move ${d.title} to a knowledge base`}
                  value={d.knowledge_base_id || ""}
                  disabled={d.status !== "ready" || busyDocumentId === d.id}
                  title={d.status !== "ready" ? "Only ready documents can be moved" : ""}
                  onChange={(event) => move(d.id, event.target.value)}
                >
                  <option value="">All documents</option>
                  {knowledgeBases.map((knowledgeBase) => (
                    <option key={knowledgeBase.id} value={knowledgeBase.id}>
                      {knowledgeBase.name}
                    </option>
                  ))}
                </select>
              </td>
              <td>
                <button
                  onClick={() => reindex(d.id)}
                  disabled={d.status === "pending" || d.status === "processing"}
                >
                  Re-index
                </button>
                <button onClick={() => remove(d.id)}>Delete</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
