import React, { useEffect, useState } from "react";
import { api, isAuthenticated, setTokens } from "./api.js";
import Login from "./components/Login.jsx";
import Chat from "./components/Chat.jsx";
import Documents from "./components/Documents.jsx";
import Dashboard from "./components/Dashboard.jsx";
import KnowledgeBases from "./components/KnowledgeBases.jsx";
import Settings from "./components/Settings.jsx";

export default function App() {
  const [authed, setAuthed] = useState(isAuthenticated());
  const [tab, setTab] = useState("chat");
  const [user, setUser] = useState(null);
  const [knowledgeBases, setKnowledgeBases] = useState([]);
  const [selectedKnowledgeBaseId, setSelectedKnowledgeBaseId] = useState("");

  async function loadKnowledgeBases() {
    const items = await api("/knowledge-bases");
    setKnowledgeBases(items);
    if (
      selectedKnowledgeBaseId &&
      !items.some((knowledgeBase) => knowledgeBase.id === selectedKnowledgeBaseId)
    ) {
      setSelectedKnowledgeBaseId("");
    }
  }

  useEffect(() => {
    if (!authed) return;
    Promise.all([api("/auth/me"), loadKnowledgeBases()])
      .then(([currentUser]) => setUser(currentUser))
      .catch(() => {
        setTokens(null);
        setAuthed(false);
      });
  }, [authed]);

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  return (
    <div className="app">
      <header>
        <h1>Cortex</h1>
        <nav>
          <button className={tab === "chat" ? "active" : ""} onClick={() => setTab("chat")}>
            Chat
          </button>
          <button className={tab === "docs" ? "active" : ""} onClick={() => setTab("docs")}>
            Documents
          </button>
          <button
            className={tab === "knowledge-bases" ? "active" : ""}
            onClick={() => setTab("knowledge-bases")}
          >
            Knowledge bases
          </button>
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
            Settings
          </button>
          {user?.role === "admin" && (
            <button className={tab === "dashboard" ? "active" : ""} onClick={() => setTab("dashboard")}>
              Dashboard
            </button>
          )}
          <button
            onClick={() => {
              setTokens(null);
              setAuthed(false);
            }}
          >
            Logout
          </button>
        </nav>
      </header>
      <div className="workspace-filter">
        <label htmlFor="active-knowledge-base">Current knowledge base</label>
        <select
          id="active-knowledge-base"
          value={selectedKnowledgeBaseId}
          onChange={(event) => setSelectedKnowledgeBaseId(event.target.value)}
        >
          <option value="">All my documents</option>
          {knowledgeBases.map((knowledgeBase) => (
            <option key={knowledgeBase.id} value={knowledgeBase.id}>
              {knowledgeBase.name}
            </option>
          ))}
        </select>
      </div>
      <main>
        {tab === "chat" ? (
          <Chat
            knowledgeBaseId={selectedKnowledgeBaseId || null}
            onKnowledgeBaseChange={setSelectedKnowledgeBaseId}
          />
        ) : tab === "docs" ? (
          <Documents
            knowledgeBaseId={selectedKnowledgeBaseId || null}
            knowledgeBases={knowledgeBases}
            onKnowledgeBasesChanged={loadKnowledgeBases}
          />
        ) : tab === "knowledge-bases" ? (
          <KnowledgeBases
            knowledgeBases={knowledgeBases}
            onChanged={loadKnowledgeBases}
          />
        ) : tab === "settings" ? (
          <Settings />
        ) : (
          <Dashboard />
        )}
      </main>
    </div>
  );
}
