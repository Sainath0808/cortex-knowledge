import React, { useState } from "react";
import { api, setTokens } from "../api.js";

export default function Login({ onLogin }) {
  const [email, setEmail] = useState("demo@cortex.local");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState("login");
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      if (mode === "register") {
        await api("/auth/register", { method: "POST", body: { email, password } });
      }
      const tokens = await api("/auth/login", { method: "POST", body: { email, password } });
      setTokens(tokens);
      onLogin();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="login">
      <form onSubmit={submit}>
        <h1>Cortex</h1>
        <p>Enterprise Knowledge Copilot</p>
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
        />
        {error && <div className="error">{error}</div>}
        <button type="submit">{mode === "login" ? "Sign in" : "Create account"}</button>
        <a onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need an account?" : "Have an account?"}
        </a>
      </form>
    </div>
  );
}
