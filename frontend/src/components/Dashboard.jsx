import React, { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";

function formatMetric(value) {
  if (typeof value === "number") return Number.isInteger(value) ? value : value.toFixed(3);
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function Dashboard() {
  const [usage, setUsage] = useState([]);
  const [evaluations, setEvaluations] = useState([]);
  const [days, setDays] = useState(7);
  const [usageError, setUsageError] = useState("");
  const [evaluationError, setEvaluationError] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);

  async function load() {
    setLoading(true);
    setUsageError("");
    setEvaluationError("");
    const [usageResult, evaluationResult] = await Promise.allSettled([
      api(`/admin/usage?days=${days}`),
      api("/admin/evals?limit=20"),
    ]);
    if (usageResult.status === "fulfilled") {
      setUsage(usageResult.value);
    } else {
      setUsageError(usageResult.reason.message);
    }
    if (evaluationResult.status === "fulfilled") {
      setEvaluations(evaluationResult.value);
    } else {
      setEvaluationError(evaluationResult.reason.message);
    }
    if (usageResult.status === "fulfilled" || evaluationResult.status === "fulfilled") {
      setLastUpdated(new Date());
    }
    setLoading(false);
  }

  useEffect(() => {
    load();
  }, [days]);

  const summary = useMemo(() => {
    const totals = usage.reduce(
      (result, row) => {
        const calls = Number(row.calls || 0);
        result.calls += calls;
        result.promptTokens += Number(row.prompt_tokens || 0);
        result.completionTokens += Number(row.completion_tokens || 0);
        result.cost += Number(row.cost_usd || 0);
        result.weightedLatency += Number(row.avg_latency_ms || 0) * calls;
        return result;
      },
      { calls: 0, promptTokens: 0, completionTokens: 0, cost: 0, weightedLatency: 0 },
    );
    return {
      ...totals,
      averageLatency: totals.calls ? totals.weightedLatency / totals.calls : 0,
      tokens: totals.promptTokens + totals.completionTokens,
    };
  }, [usage]);

  const operationCosts = useMemo(() => {
    const costs = usage.reduce((result, row) => {
      result[row.operation] = (result[row.operation] || 0) + Number(row.cost_usd || 0);
      return result;
    }, {});
    return Object.entries(costs).sort((a, b) => b[1] - a[1]);
  }, [usage]);
  const maxOperationCost = Math.max(...operationCosts.map(([, cost]) => cost), 0);

  return (
    <section className="dashboard">
      <div className="dashboard-heading">
        <div>
          <h2>Usage and evaluations</h2>
          {lastUpdated && (
            <p className="dashboard-updated">Updated {lastUpdated.toLocaleTimeString()}</p>
          )}
        </div>
        <div className="dashboard-controls">
          <label htmlFor="usage-period">Usage period</label>
          <select
            id="usage-period"
            value={days}
            onChange={(event) => setDays(Number(event.target.value))}
          >
            <option value={7}>7 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
          <button type="button" onClick={load} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <h3>LLM usage · last {days} days</h3>
      {usageError && <p className="error">{usageError}</p>}
      <div className="usage-summary">
        <article><span>Model calls</span><strong>{summary.calls.toLocaleString()}</strong></article>
        <article><span>Total tokens</span><strong>{summary.tokens.toLocaleString()}</strong></article>
        <article><span>Estimated cost</span><strong>${summary.cost.toFixed(4)}</strong></article>
        <article><span>Avg. latency</span><strong>{summary.averageLatency.toFixed(0)} ms</strong></article>
      </div>

      {operationCosts.length > 0 && (
        <div className="operation-costs">
          <h4>Estimated cost by operation</h4>
          {operationCosts.map(([operation, cost]) => (
            <div className="operation-cost" key={operation}>
              <span>{operation}</span>
              <div className="operation-cost-track">
                <div
                  className="operation-cost-fill"
                  style={{ width: `${maxOperationCost ? (cost / maxOperationCost) * 100 : 0}%` }}
                />
              </div>
              <strong>${cost.toFixed(4)}</strong>
            </div>
          ))}
        </div>
      )}

      {usage.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Operation</th><th>Model</th><th>Calls</th><th>Prompt tokens</th><th>Completion tokens</th><th>Cost (USD)</th><th>Avg latency</th></tr>
            </thead>
            <tbody>
              {usage.map((row) => (
                <tr key={`${row.operation}-${row.model}`}>
                  <td>{row.operation}</td>
                  <td>{row.model}</td>
                  <td>{row.calls}</td>
                  <td>{Number(row.prompt_tokens ?? 0).toLocaleString()}</td>
                  <td>{Number(row.completion_tokens ?? 0).toLocaleString()}</td>
                  <td>${Number(row.cost_usd ?? 0).toFixed(4)}</td>
                  <td>{Number(row.avg_latency_ms ?? 0).toFixed(0)} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !usageError ? (
        <p className="dashboard-empty">No usage records for this period.</p>
      ) : null}

      <h3>Evaluation runs</h3>
      {evaluationError && <p className="error">{evaluationError}</p>}
      {evaluations.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Date</th><th>Kind</th><th>Dataset size</th><th>Metrics</th></tr>
            </thead>
            <tbody>
              {evaluations.map((run) => (
                <tr key={run.id}>
                  <td>{new Date(run.created_at).toLocaleString()}</td>
                  <td>{run.kind}</td>
                  <td>{run.dataset_size}</td>
                  <td>
                    <div className="eval-metrics">
                      {Object.entries(run.metrics || {}).map(([name, value]) => (
                        <span key={name}><b>{name.replaceAll("_", " ")}:</b> {formatMetric(value)}</span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : !evaluationError ? (
        <p className="dashboard-empty">No evaluation runs have been recorded.</p>
      ) : null}
    </section>
  );
}
