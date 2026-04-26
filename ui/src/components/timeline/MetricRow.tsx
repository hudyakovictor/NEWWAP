import { COL_W, LABEL_W, METRIC_H_MIN } from "./constants";
import type { MetricConfig } from "../../mock/data";
import { SeverityIcon } from "./icons";

const VB_H = 100;

export default function MetricRow({
  metric,
  years,
  selectedYear,
  onSelect,
  grow = 1,
}: {
  metric: MetricConfig;
  years: number[];
  selectedYear: number;
  onSelect: (y: number) => void;
  grow?: number;
}) {
  const width = years.length * COL_W;
  const [dmin, dmax] = metric.domain ?? [
    Math.min(...metric.values),
    Math.max(...metric.values),
  ];
  const yFromValue = (v: number) => {
    const pad = 14;
    const h = VB_H - pad * 2;
    const t = (v - dmin) / (dmax - dmin || 1);
    return VB_H - pad - t * h;
  };

  const points = metric.values.map((v, i) => ({
    x: i * COL_W + COL_W / 2,
    y: yFromValue(v),
    v,
  }));

  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`).join(" ");

  return (
    <div
      className="flex border-b border-line/40 shrink-0"
      style={{ flexGrow: grow, flexBasis: 0, minHeight: METRIC_H_MIN }}
    >
      <div
        style={{ width: LABEL_W }}
        className="flex flex-col justify-center px-3 border-r border-line/60"
      >
        <div className="text-[11px] text-white truncate">{metric.title}</div>
        <div className="text-[10px] text-muted truncate">
          {metric.subtitle}
          {metric.unit ? ` · ${metric.unit}` : ""}
        </div>
      </div>

      <div className="relative h-full" style={{ width }}>
        <svg
          viewBox={`0 0 ${width} ${VB_H}`}
          preserveAspectRatio="none"
          className="absolute inset-0 w-full h-full pointer-events-none"
        >
          <line
            x1={0}
            x2={width}
            y1={VB_H - 14}
            y2={VB_H - 14}
            stroke="#1a2b44"
            strokeDasharray="2 3"
            vectorEffect="non-scaling-stroke"
          />
          {metric.kind === "bar" ? (
            points.map((p, i) => {
              const baseY = VB_H - 14;
              const h = Math.max(1, baseY - p.y);
              return (
                <rect
                  key={i}
                  x={p.x - 4}
                  y={baseY - h}
                  width={8}
                  height={h}
                  fill={metric.color}
                  opacity={0.75}
                />
              );
            })
          ) : (
            <>
              <path
                d={path}
                stroke={metric.color}
                strokeWidth={1.3}
                fill="none"
                vectorEffect="non-scaling-stroke"
              />
              {points.map((p, i) => (
                <circle key={i} cx={p.x} cy={p.y} r={2.2} fill={metric.color} />
              ))}
            </>
          )}
        </svg>

        <div className="absolute inset-0 flex">
          {years.map((y, i) => {
            const selected = y === selectedYear;
            const flag = metric.flags?.[i];
            const v = metric.values[i];
            const formatted =
              metric.domain && metric.domain[1] <= 1
                ? v.toFixed(2)
                : Number.isInteger(v)
                ? String(v)
                : v.toFixed(v >= 100 ? 1 : 2);
            return (
              <button
                key={y}
                onClick={() => onSelect(y)}
                style={{ width: COL_W }}
                className={`relative h-full flex flex-col items-center ${
                  selected ? "bg-danger/10" : ""
                }`}
              >
                <span
                  className="text-[10px] font-mono mt-0.5"
                  style={{ color: metric.color }}
                >
                  {formatted}
                </span>
                {flag && (
                  <span className="absolute bottom-0.5">
                    <SeverityIcon s={flag} />
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
