// Thin API client: token storage, auto-refresh on 401, JSON helpers.
const BASE = "/api/v1";

let accessToken = localStorage.getItem("access_token");
let refreshToken = localStorage.getItem("refresh_token");

export function setTokens(tokens) {
  accessToken = tokens?.access_token ?? null;
  refreshToken = tokens?.refresh_token ?? null;
  if (accessToken) {
    localStorage.setItem("access_token", accessToken);
    localStorage.setItem("refresh_token", refreshToken);
  } else {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  }
}

export function isAuthenticated() {
  return Boolean(accessToken);
}

async function tryRefresh() {
  if (!refreshToken) return false;
  const resp = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!resp.ok) return false;
  setTokens(await resp.json());
  return true;
}

export async function api(path, { method = "GET", body, isForm = false } = {}) {
  const doFetch = () =>
    fetch(`${BASE}${path}`, {
      method,
      headers: {
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...(body && !isForm ? { "Content-Type": "application/json" } : {}),
      },
      body: isForm ? body : body ? JSON.stringify(body) : undefined,
    });

  let resp = await doFetch();
  if (resp.status === 401 && (await tryRefresh())) {
    resp = await doFetch();
  }
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => ({}))).detail ?? resp.statusText;
    throw new Error(detail);
  }
  return resp.status === 204 ? null : resp.json();
}

export async function streamChat(body, onEvent, signal) {
  const doFetch = () =>
    fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });

  let resp = await doFetch();
  if (resp.status === 401 && (await tryRefresh())) {
    resp = await doFetch();
  }
  if (!resp.ok) {
    const detail = (await resp.json().catch(() => ({}))).detail ?? resp.statusText;
    throw new Error(detail);
  }
  if (!resp.body) throw new Error("Streaming is unavailable in this browser.");

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function dispatch(block) {
    let event = "message";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length) onEvent(event, data.join("\n"));
  }

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
      boundary = buffer.indexOf("\n\n");
    }
    if (done) break;
  }
  if (buffer.trim()) dispatch(buffer);
}
