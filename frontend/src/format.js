// Number, money and date formatting used across the dashboard.

const usd2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
const whole = new Intl.NumberFormat("en-US");

/** "$12.34"; tiny amounts keep 4 decimals so a $0.0021 request does not show as $0.00. */
export function formatUsd(value) {
  const n = Number(value) || 0;
  if (n > 0 && n < 0.01) return `$${n.toFixed(4)}`;
  return usd2.format(n);
}

/** 1,284 -> "1.3K" (stat tiles) */
export function formatCompact(value) {
  return compact.format(Number(value) || 0);
}

/** 1284 -> "1,284" (tables) */
export function formatNumber(value) {
  return whole.format(Number(value) || 0);
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function formatDate(iso) {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/** "2026-11" for the current month in the browser's time zone. */
export function currentMonth() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}
