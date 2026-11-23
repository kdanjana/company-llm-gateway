import { useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import BudgetMeter from "../components/BudgetMeter.jsx";
import DailyCostChart from "../components/DailyCostChart.jsx";
import ErrorBox from "../components/ErrorBox.jsx";
import { currentMonth, formatCompact, formatNumber, formatUsd } from "../format.js";
import { useLoad } from "../useLoad.js";

function addUp(rows) {
  const total = { spend: 0, requests: 0, cached: 0, blocked: 0, errors: 0, pii_masked: 0 };
  for (const r of rows) {
    total.spend += Number(r.spend_usd);
    total.requests += r.requests;
    total.cached += r.cached;
    total.blocked += r.blocked;
    total.errors += r.errors;
    total.pii_masked += r.pii_masked;
  }
  return total;
}

/** Only the highest alert per department (100% replaces 80%). */
function latestAlerts(alerts) {
  const byDepartment = new Map();
  for (const a of alerts) {
    const current = byDepartment.get(a.department);
    if (!current || a.level > current.level) byDepartment.set(a.department, a);
  }
  return [...byDepartment.values()];
}

export default function OverviewPage() {
  const { me } = useAuth();
  const isAdmin = me.role === "admin";
  const [month, setMonth] = useState(currentMonth());
  const [department, setDepartment] = useState(""); // admins: "" = all departments

  const summary = useLoad(() => api.summary(month), [month]);
  const daily = useLoad(() => api.daily(month, department), [month, department]);
  const models = useLoad(() => api.modelsUsage(month, department), [month, department]);
  const alerts = useLoad(() => api.alerts(month), [month]);

  const allRows = summary.data?.departments ?? [];
  const rows = department ? allRows.filter((r) => String(r.id) === department) : allRows;
  const shownNames = new Set(rows.map((r) => r.name));
  const total = addUp(rows);
  const banners = latestAlerts((alerts.data?.alerts ?? []).filter((a) => shownNames.has(a.department)));

  return (
    <div className="page">
      <div className="page-head">
        <h1>Overview</h1>
        {/* Filters: one row, above everything they scope. */}
        <div className="filters">
          <label>
            Month
            <input type="month" value={month} onChange={(e) => setMonth(e.target.value || currentMonth())} />
          </label>
          {isAdmin && (
            <label>
              Department
              <select value={department} onChange={(e) => setDepartment(e.target.value)}>
                <option value="">All departments</option>
                {allRows.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </div>

      <ErrorBox message={summary.error || daily.error || models.error || alerts.error} />

      {banners.map((a) => (
        <div key={a.id} className={`notice ${a.level >= 100 ? "critical" : "warning"}`} role="status">
          <span aria-hidden="true">{a.level >= 100 ? "⛔" : "⚠"}</span>{" "}
          {a.level >= 100
            ? `${a.department} has used its whole monthly budget. Its requests are blocked until an admin raises the budget.`
            : `${a.department} has used ${a.level}% of its monthly budget.`}
        </div>
      ))}

      <section className={`tiles${summary.loading ? " reloading" : ""}`}>
        <div className="card tile hero">
          <span className="tile-label">Spend this month</span>
          <span className="hero-value">{formatUsd(total.spend)}</span>
        </div>
        <div className="card tile">
          <span className="tile-label">Requests</span>
          <span className="tile-value">{formatCompact(total.requests)}</span>
        </div>
        <div className="card tile">
          <span className="tile-label">Answered from cache</span>
          <span className="tile-value">{formatCompact(total.cached)}</span>
        </div>
        <div className="card tile">
          <span className="tile-label">Blocked by budget</span>
          <span className="tile-value">{formatCompact(total.blocked)}</span>
        </div>
        <div className="card tile">
          <span className="tile-label">Errors</span>
          <span className="tile-value">{formatCompact(total.errors)}</span>
        </div>
        <div className="card tile">
          <span className="tile-label">Personal data items masked</span>
          <span className="tile-value">{formatCompact(total.pii_masked)}</span>
        </div>
      </section>

      <section className={`card${summary.loading ? " reloading" : ""}`}>
        <h2>Budgets</h2>
        {rows.length === 0 && !summary.loading && <p className="muted">No departments yet.</p>}
        {rows.map((r) => (
          <BudgetMeter
            key={r.id}
            name={r.name}
            spend={r.spend_usd}
            budget={r.monthly_budget_usd}
            percent={r.percent_used ?? 0}
          />
        ))}
      </section>

      <section className={`card${daily.loading ? " reloading" : ""}`}>
        <h2>Cost per day (USD)</h2>
        {daily.data && <DailyCostChart days={daily.data.days} />}
      </section>

      <section className={`card${models.loading ? " reloading" : ""}`}>
        <h2>Usage by model</h2>
        {models.data && models.data.models.length === 0 && <p className="muted">No requests this month.</p>}
        {models.data && models.data.models.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th className="num">Requests</th>
                  <th className="num">Cached</th>
                  <th className="num">Fallbacks</th>
                  <th className="num">Errors</th>
                  <th className="num">Input tokens</th>
                  <th className="num">Output tokens</th>
                  <th className="num">Avg answer time</th>
                  <th className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {models.data.models.map((m) => (
                  <tr key={m.model_id}>
                    <td className="mono">{m.model_id}</td>
                    <td className="num">{formatNumber(m.requests)}</td>
                    <td className="num">{formatNumber(m.cached)}</td>
                    <td className="num">{formatNumber(m.fallbacks)}</td>
                    <td className="num">{formatNumber(m.errors)}</td>
                    <td className="num">{formatNumber(m.input_tokens)}</td>
                    <td className="num">{formatNumber(m.output_tokens)}</td>
                    <td className="num">{m.avg_latency_ms === null ? "—" : `${formatNumber(m.avg_latency_ms)} ms`}</td>
                    <td className="num">{formatUsd(m.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
