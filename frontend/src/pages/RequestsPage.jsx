import { useEffect, useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import ErrorBox from "../components/ErrorBox.jsx";
import StatusBadge from "../components/StatusBadge.jsx";
import { formatDateTime, formatNumber, formatUsd } from "../format.js";
import { useLoad } from "../useLoad.js";

const PAGE_SIZE = 50;

export default function RequestsPage() {
  const { me } = useAuth();
  const isAdmin = me.role === "admin";
  const [department, setDepartment] = useState("");
  const [status, setStatus] = useState("");
  const [rows, setRows] = useState([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const departments = useLoad(() => (isAdmin ? api.departments() : Promise.resolve([])), [isAdmin]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    api
      .requests({ department, status, limit: PAGE_SIZE, offset: 0 })
      .then((data) => {
        if (cancelled) return;
        setRows(data.results);
        setCount(data.count);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [department, status]);

  async function loadMore() {
    setLoading(true);
    try {
      const data = await api.requests({ department, status, limit: PAGE_SIZE, offset: rows.length });
      setRows((current) => [...current, ...data.results]);
      setCount(data.count);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Requests</h1>
        <div className="filters">
          {isAdmin && (
            <label>
              Department
              <select value={department} onChange={(e) => setDepartment(e.target.value)}>
                <option value="">All departments</option>
                {(departments.data ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label>
            Status
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Any</option>
              <option value="ok">OK</option>
              <option value="error">Error</option>
              <option value="blocked">Blocked</option>
            </select>
          </label>
        </div>
      </div>

      <ErrorBox message={error} />

      <section className={`card${loading ? " reloading" : ""}`}>
        <p className="muted">
          {formatNumber(count)} request{count === 1 ? "" : "s"}. The prompts and answers themselves are never stored.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                {isAdmin && <th>Department</th>}
                <th>App (key)</th>
                <th>Model</th>
                <th>Status</th>
                <th className="num">Tokens in / out</th>
                <th className="num">Cost</th>
                <th className="num">Answer time</th>
                <th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>{formatDateTime(r.created_at)}</td>
                  {isAdmin && <td>{r.department}</td>}
                  <td>{r.api_key ?? "—"}</td>
                  <td className="mono">
                    {r.model_id}
                    {r.fallback_used && <div className="muted">→ {r.served_model_id} (fallback)</div>}
                  </td>
                  <td>
                    <StatusBadge status={r.status} />
                    {r.error_code && <div className="muted">{r.error_code}</div>}
                  </td>
                  <td className="num">
                    {formatNumber(r.input_tokens)} / {formatNumber(r.output_tokens)}
                  </td>
                  <td className="num">{formatUsd(r.cost_usd)}</td>
                  <td className="num">{r.cached || r.status !== "ok" ? "—" : `${formatNumber(r.latency_ms)} ms`}</td>
                  <td className="notes">
                    {r.cached && <span className="tag">cached</span>}
                    {r.streamed && <span className="tag">streamed</span>}
                    {r.pii_masked_count > 0 && <span className="tag">{r.pii_masked_count} masked</span>}
                  </td>
                </tr>
              ))}
              {rows.length === 0 && !loading && (
                <tr>
                  <td colSpan={9} className="muted">
                    No requests match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {rows.length < count && (
          <button type="button" className="button" onClick={loadMore} disabled={loading}>
            Load more
          </button>
        )}
      </section>
    </div>
  );
}
