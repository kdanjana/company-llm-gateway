import { formatUsd } from "../format.js";

/**
 * One department's spend against its monthly budget.
 * The fill carries the severity (normal -> warning at the alert level -> critical at 100%),
 * and the track is a lighter tint of the same color. The state is also written as icon + text.
 */
export default function BudgetMeter({ name, spend, budget, percent, alertPercent = 80 }) {
  if (budget === null || budget === undefined) {
    return (
      <div className="meter-row">
        <div className="meter-head">
          <span className="meter-name">{name}</span>
          <span className="muted">{formatUsd(spend)} · no limit</span>
        </div>
      </div>
    );
  }

  const tone = percent >= 100 ? "critical" : percent >= alertPercent ? "warning" : "normal";
  const state =
    tone === "critical" ? { icon: "⛔", text: "Budget used up · requests blocked" } : tone === "warning" ? { icon: "⚠", text: "Near the limit" } : null;

  return (
    <div className="meter-row">
      <div className="meter-head">
        <span className="meter-name">{name}</span>
        <span>
          <strong>{formatUsd(spend)}</strong> <span className="muted">of {formatUsd(budget)}</span>
        </span>
      </div>
      <div
        className={`meter ${tone}`}
        role="meter"
        aria-label={`${name} budget used`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.min(100, Math.round(percent))}
      >
        <div className="meter-fill" style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
      <div className="meter-foot">
        <span>{percent.toFixed(0)}% used</span>
        {state && (
          <span className={`state ${tone}`}>
            <span aria-hidden="true">{state.icon}</span> {state.text}
          </span>
        )}
      </div>
    </div>
  );
}
