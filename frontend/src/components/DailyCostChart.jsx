import { useEffect, useRef, useState } from "react";
import { formatDate, formatNumber, formatUsd } from "../format.js";

// Column chart of cost per day (one series, so no legend: the card title names it).
// Columns: <= 24px wide, 4px rounded top, square at the baseline, 2px gap between neighbours.
// Hover or keyboard focus on a day shows its exact cost and request count. "Show table" lists every value.

const HEIGHT = 220;
const MARGIN = { top: 12, right: 8, bottom: 28, left: 56 };

function niceStep(max, count = 4) {
  const raw = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalized = raw / magnitude;
  const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

/** Column path: rounded top corners, square bottom (sits on the baseline). */
function columnPath(x, y, w, h, r) {
  const radius = Math.min(r, w / 2, h);
  return `M${x},${y + h} V${y + radius} Q${x},${y} ${x + radius},${y} H${x + w - radius} Q${x + w},${y} ${x + w},${y + radius} V${y + h} Z`;
}

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    if (!ref.current) return undefined;
    const observer = new ResizeObserver((entries) => {
      setWidth(entries[0].contentRect.width);
    });
    observer.observe(ref.current);
    return () => {
      observer.disconnect();
    };
  }, []);
  return [ref, width];
}

export default function DailyCostChart({ days }) {
  const [ref, width] = useWidth();
  const [active, setActive] = useState(null); // index of the hovered/focused day
  const [showTable, setShowTable] = useState(false);

  const values = days.map((d) => Number(d.cost_usd));
  const maxValue = Math.max(...values, 0);
  const step = niceStep(maxValue > 0 ? maxValue : 0.01);
  const yMax = Math.max(step, Math.ceil(maxValue / step) * step);
  const ticks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, i) => i * step);
  const decimals = step >= 1 ? 0 : Math.min(4, Math.ceil(-Math.log10(step)));

  const plotW = Math.max(100, width - MARGIN.left - MARGIN.right);
  const plotH = HEIGHT - MARGIN.top - MARGIN.bottom;
  const band = plotW / Math.max(1, days.length);
  const barW = Math.max(2, Math.min(24, band - 2));
  const y = (v) => MARGIN.top + plotH - (v / yMax) * plotH;
  const labelEvery = days.length > 20 ? 5 : 1;

  const activeDay = active === null ? null : days[active];
  const tooltipLeft = active === null ? 0 : Math.min(Math.max(MARGIN.left + band * (active + 0.5), 70), width - 70);

  return (
    <div className="chart">
      <div className="chart-plot" ref={ref} onPointerLeave={() => setActive(null)}>
        <svg width={width} height={HEIGHT} role="img" aria-label="Cost per day">
          {ticks.map((t) => (
            <g key={t}>
              <line className={t === 0 ? "axis-line" : "grid-line"} x1={MARGIN.left} x2={MARGIN.left + plotW} y1={y(t)} y2={y(t)} />
              <text className="axis-label" x={MARGIN.left - 8} y={y(t)} dy="0.32em" textAnchor="end">
                ${t.toFixed(decimals)}
              </text>
            </g>
          ))}

          {days.map((d, i) => {
            const value = values[i];
            const x = MARGIN.left + band * i + (band - barW) / 2;
            const h = (value / yMax) * plotH;
            const isActive = active === i;
            return (
              <g key={d.date}>
                {value > 0 && (
                  <path className={`column${isActive ? " active" : ""}`} d={columnPath(x, y(value), barW, h, 4)} />
                )}
                {/* The hit area is the whole day band (bigger than the column itself). */}
                <rect
                  className="hit"
                  x={MARGIN.left + band * i}
                  y={MARGIN.top}
                  width={band}
                  height={plotH}
                  tabIndex={0}
                  aria-label={`${formatDate(d.date)}: ${formatUsd(d.cost_usd)}, ${d.requests} requests`}
                  onPointerEnter={() => setActive(i)}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                />
                {(i % labelEvery === 0 || i === days.length - 1) && (
                  <text className="axis-label" x={MARGIN.left + band * (i + 0.5)} y={HEIGHT - 8} textAnchor="middle">
                    {Number(d.date.slice(8))}
                  </text>
                )}
              </g>
            );
          })}
        </svg>

        {activeDay && (
          <div className="tooltip" style={{ left: tooltipLeft }}>
            <strong>{formatUsd(activeDay.cost_usd)}</strong>
            <span className="muted">
              {formatDate(activeDay.date)} · {formatNumber(activeDay.requests)} requests
            </span>
          </div>
        )}
      </div>

      <button type="button" className="button link" onClick={() => setShowTable((v) => !v)}>
        {showTable ? "Hide table" : "Show table"}
      </button>
      {showTable && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th className="num">Requests</th>
                <th className="num">Cost</th>
              </tr>
            </thead>
            <tbody>
              {days.map((d) => (
                <tr key={d.date}>
                  <td>{formatDate(d.date)}</td>
                  <td className="num">{formatNumber(d.requests)}</td>
                  <td className="num">{formatUsd(d.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
