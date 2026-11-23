import { useState } from "react";
import { api } from "../api.js";
import ErrorBox from "../components/ErrorBox.jsx";
import { useLoad } from "../useLoad.js";

// Admin only: department budgets, and which models are allowed with their prices and fallback.

function DepartmentRow({ department, onSaved, onError }) {
  const [budget, setBudget] = useState(department.monthly_budget_usd ?? "");
  const [active, setActive] = useState(department.is_active);
  const [saved, setSaved] = useState(false);
  const changed = String(budget) !== String(department.monthly_budget_usd ?? "") || active !== department.is_active;

  async function save() {
    onError("");
    try {
      await api.updateDepartment(department.id, { monthly_budget_usd: budget === "" ? null : budget, is_active: active });
      setSaved(true);
      onSaved();
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <tr>
      <td>{department.name}</td>
      <td>
        <input
          type="number"
          min="0"
          step="0.01"
          value={budget}
          placeholder="No limit"
          onChange={(e) => {
            setBudget(e.target.value);
            setSaved(false);
          }}
          aria-label={`Monthly budget for ${department.name} in USD`}
        />
      </td>
      <td>
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => {
            setActive(e.target.checked);
            setSaved(false);
          }}
          aria-label={`${department.name} is active`}
        />
      </td>
      <td>
        <button type="button" className="button" onClick={save} disabled={!changed}>
          Save
        </button>
        {saved && !changed && <span className="muted"> Saved ✓</span>}
      </td>
    </tr>
  );
}

function ModelRow({ model, allModels, onSaved, onError }) {
  const [input, setInput] = useState(model.input_price_per_1k);
  const [output, setOutput] = useState(model.output_price_per_1k);
  const [fallback, setFallback] = useState(model.fallback_model_id);
  const [enabled, setEnabled] = useState(model.is_enabled);
  const [saved, setSaved] = useState(false);
  const changed =
    input !== model.input_price_per_1k ||
    output !== model.output_price_per_1k ||
    fallback !== model.fallback_model_id ||
    enabled !== model.is_enabled;

  function edit(setter) {
    return (value) => {
      setter(value);
      setSaved(false);
    };
  }

  async function save() {
    onError("");
    try {
      await api.updateModel(model.id, {
        input_price_per_1k: input,
        output_price_per_1k: output,
        fallback_model_id: fallback,
        is_enabled: enabled,
      });
      setSaved(true);
      onSaved();
    } catch (err) {
      onError(err.message);
    }
  }

  return (
    <tr>
      <td className="mono">{model.model_id}</td>
      <td>
        <input type="number" min="0" step="0.000001" value={input} onChange={(e) => edit(setInput)(e.target.value)} aria-label="Input price per 1,000 tokens" />
      </td>
      <td>
        <input type="number" min="0" step="0.000001" value={output} onChange={(e) => edit(setOutput)(e.target.value)} aria-label="Output price per 1,000 tokens" />
      </td>
      <td>
        <select value={fallback} onChange={(e) => edit(setFallback)(e.target.value)} aria-label="Fallback model">
          <option value="">None</option>
          {allModels
            .filter((m) => m.model_id !== model.model_id)
            .map((m) => (
              <option key={m.id} value={m.model_id}>
                {m.model_id}
              </option>
            ))}
        </select>
      </td>
      <td>
        <input type="checkbox" checked={enabled} onChange={(e) => edit(setEnabled)(e.target.checked)} aria-label="Enabled" />
      </td>
      <td>
        <button type="button" className="button" onClick={save} disabled={!changed}>
          Save
        </button>
        {saved && !changed && <span className="muted"> Saved ✓</span>}
      </td>
    </tr>
  );
}

export default function SettingsPage() {
  const departments = useLoad(() => api.departments(), []);
  const models = useLoad(() => api.models(), []);
  const [error, setError] = useState("");

  const [newDepartment, setNewDepartment] = useState({ name: "", monthly_budget_usd: "" });
  const [newModel, setNewModel] = useState({ model_id: "", input_price_per_1k: "", output_price_per_1k: "" });

  async function addDepartment(event) {
    event.preventDefault();
    setError("");
    try {
      await api.createDepartment({
        name: newDepartment.name,
        monthly_budget_usd: newDepartment.monthly_budget_usd === "" ? null : newDepartment.monthly_budget_usd,
      });
      setNewDepartment({ name: "", monthly_budget_usd: "" });
      departments.reload();
    } catch (err) {
      setError(err.message);
    }
  }

  async function addModel(event) {
    event.preventDefault();
    setError("");
    try {
      await api.createModel(newModel);
      setNewModel({ model_id: "", input_price_per_1k: "", output_price_per_1k: "" });
      models.reload();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>Settings</h1>
      </div>
      <ErrorBox message={error || departments.error || models.error} />

      <section className="card">
        <h2>Department budgets</h2>
        <p className="muted">Monthly limit in USD. Alert at 80%; at 100% the department's requests are blocked. Leave empty for no limit.</p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Department</th>
                <th>Monthly budget (USD)</th>
                <th>Active</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(departments.data ?? []).map((d) => (
                <DepartmentRow key={`${d.id}-${d.monthly_budget_usd}-${d.is_active}`} department={d} onSaved={departments.reload} onError={setError} />
              ))}
            </tbody>
          </table>
        </div>
        <form className="form-row" onSubmit={addDepartment}>
          <label>
            New department
            <input value={newDepartment.name} onChange={(e) => setNewDepartment({ ...newDepartment, name: e.target.value })} required maxLength={100} />
          </label>
          <label>
            Monthly budget (USD)
            <input
              type="number"
              min="0"
              step="0.01"
              placeholder="No limit"
              value={newDepartment.monthly_budget_usd}
              onChange={(e) => setNewDepartment({ ...newDepartment, monthly_budget_usd: e.target.value })}
            />
          </label>
          <button type="submit" className="button primary">
            Add department
          </button>
        </form>
      </section>

      <section className="card">
        <h2>Models and prices</h2>
        <p className="muted">
          Only models listed here can be used. Prices are USD per 1,000 tokens, from the AWS Bedrock pricing page. The fallback model is tried once when a
          model is rate-limited or unavailable.
        </p>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Model ID</th>
                <th>Input / 1K</th>
                <th>Output / 1K</th>
                <th>Fallback</th>
                <th>Enabled</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {(models.data ?? []).map((m) => (
                <ModelRow key={`${m.id}-${m.updated_at}`} model={m} allModels={models.data} onSaved={models.reload} onError={setError} />
              ))}
            </tbody>
          </table>
        </div>
        <form className="form-row" onSubmit={addModel}>
          <label>
            Model ID
            <input value={newModel.model_id} onChange={(e) => setNewModel({ ...newModel, model_id: e.target.value })} required maxLength={200} />
          </label>
          <label>
            Input / 1K (USD)
            <input
              type="number"
              min="0"
              step="0.000001"
              value={newModel.input_price_per_1k}
              onChange={(e) => setNewModel({ ...newModel, input_price_per_1k: e.target.value })}
              required
            />
          </label>
          <label>
            Output / 1K (USD)
            <input
              type="number"
              min="0"
              step="0.000001"
              value={newModel.output_price_per_1k}
              onChange={(e) => setNewModel({ ...newModel, output_price_per_1k: e.target.value })}
              required
            />
          </label>
          <button type="submit" className="button primary">
            Add model
          </button>
        </form>
      </section>
    </div>
  );
}
