// Request status: always icon + label, never color alone.
const STATUS = {
  ok: { label: "OK", icon: "✓", tone: "good" },
  error: { label: "Error", icon: "✕", tone: "critical" },
  blocked: { label: "Blocked", icon: "⛔", tone: "serious" },
};

export default function StatusBadge({ status }) {
  const s = STATUS[status] ?? { label: status, icon: "•", tone: "neutral" };
  return (
    <span className={`badge ${s.tone}`}>
      <span aria-hidden="true">{s.icon}</span> {s.label}
    </span>
  );
}
