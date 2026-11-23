import { useState } from "react";
import { api } from "../api.js";
import { useAuth } from "../auth.jsx";
import ErrorBox from "../components/ErrorBox.jsx";
import { formatDateTime } from "../format.js";
import { useLoad } from "../useLoad.js";

export default function ApiKeysPage() {
  const { me } = useAuth();
  const isAdmin = me.role === "admin";
  const keys = useLoad(() => api.apiKeys(), []);
  const departments = useLoad(() => api.departments(), []);

  const [departmentId, setDepartmentId] = useState(isAdmin ? "" : String(me.department?.id ?? ""));
  const [name, setName] = useState("");
  const [newKey, setNewKey] = useState(null); // the raw key, shown once
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function create(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const created = await api.createApiKey(Number(departmentId), name);
      setNewKey(created);
      setName("");
      keys.reload();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(key) {
    if (!window.confirm(`Revoke the key "${key.name}" (${key.prefix}…)? Apps using it will stop working immediately.`)) return;
    setError("");
    try {
      await api.revokeApiKey(key.id);
      keys.reload();
    } catch (err) {
      setError(err.message);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(newKey.raw_key);
      setCopied(true);
    } catch {
      setCopied(false); // clipboard blocked: the key is still visible to copy by hand
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>API keys</h1>
      </div>
      <ErrorBox message={error || keys.error || departments.error} />

      <section className="card">
        <h2>Create a key</h2>
        <p className="muted">Each app gets its own key, so its usage shows up separately and it can be revoked on its own.</p>
        <form className="form-row" onSubmit={create}>
          {isAdmin ? (
            <label>
              Department
              <select value={departmentId} onChange={(e) => setDepartmentId(e.target.value)} required>
                <option value="" disabled>
                  Choose…
                </option>
                {(departments.data ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label>
              Department
              <input value={me.department?.name ?? ""} disabled />
            </label>
          )}
          <label>
            App name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. sales-bot" maxLength={100} required />
          </label>
          <button type="submit" className="button primary" disabled={busy}>
            Create key
          </button>
        </form>

        {newKey && (
          <div className="notice warning new-key">
            <div>
              <span aria-hidden="true">⚠</span> Copy this key now. It is shown only once and cannot be recovered.
            </div>
            <code>{newKey.raw_key}</code>
            <div className="new-key-actions">
              <button type="button" className="button" onClick={copy}>
                {copied ? "Copied ✓" : "Copy"}
              </button>
              <button type="button" className="button ghost" onClick={() => setNewKey(null)}>
                Done
              </button>
            </div>
          </div>
        )}
      </section>

      <section className={`card${keys.loading ? " reloading" : ""}`}>
        <h2>Keys</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Key</th>
                <th>App name</th>
                {isAdmin && <th>Department</th>}
                <th>Status</th>
                <th>Created</th>
                <th>Last used</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(keys.data ?? []).map((k) => (
                <tr key={k.id}>
                  <td className="mono">{k.prefix}…</td>
                  <td>{k.name}</td>
                  {isAdmin && <td>{k.department}</td>}
                  <td>
                    {k.is_active ? (
                      <span className="badge good">
                        <span aria-hidden="true">✓</span> Active
                      </span>
                    ) : (
                      <span className="badge neutral">
                        <span aria-hidden="true">–</span> Revoked
                      </span>
                    )}
                  </td>
                  <td>{formatDateTime(k.created_at)}</td>
                  <td>{formatDateTime(k.last_used_at)}</td>
                  <td>
                    {k.is_active && (
                      <button type="button" className="button danger" onClick={() => revoke(k)}>
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {keys.data && keys.data.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    No keys yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
