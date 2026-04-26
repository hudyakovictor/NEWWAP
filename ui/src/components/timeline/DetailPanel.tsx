
import type { MetricConfig, YearPoint } from "../../mock/data";

export default function DetailPanel({
  point,
  metrics,
  yearIndex,
}: {
  point: YearPoint;
  metrics: MetricConfig[];
  yearIndex: number;
}) {
  return (
    <aside className="w-72 shrink-0 border-l border-line bg-bg-panel/70 p-3 flex flex-col gap-3 overflow-auto">
      <div className="text-[10px] uppercase tracking-widest text-muted">Selected year</div>
      <div className="flex items-start gap-3">
        <img
          src={point.photo}
          alt={String(point.year)}
          className="w-20 h-20 rounded-sm object-cover border border-line"
        />
        <div className="flex-1">
          <div className="text-2xl font-semibold text-white leading-none">{point.year}</div>
          <div className="text-[11px] text-muted mt-1">photo #{yearIndex + 1} (mock)</div>
          <div className="mt-2 flex items-center gap-1 text-[10px]">
            <span
              className={`px-1.5 py-0.5 rounded ${
                point.identity === "A" ? "bg-accent/30 text-accent" : "bg-danger/30 text-danger"
              }`}
            >
              cluster {point.identity}
            </span>
            {point.anomaly && (
              <span
                className={`px-1.5 py-0.5 rounded ${
                  point.anomaly === "ok"
                    ? "bg-ok/20 text-ok"
                    : point.anomaly === "info"
                    ? "bg-info/20 text-info"
                    : point.anomaly === "warn"
                    ? "bg-warn/20 text-warn"
                    : "bg-danger/20 text-danger"
                }`}
              >
                {point.anomaly}
              </span>
            )}
          </div>
        </div>
      </div>

      {point.note && (
        <div className="text-[11px] text-muted leading-snug bg-bg-deep/60 rounded p-2 border border-line/60">
          {point.note}
        </div>
      )}

      <div>
        <div className="text-[10px] uppercase tracking-widest text-muted mb-1">Metrics</div>
        <div className="grid grid-cols-2 gap-1.5">
          {metrics.map((m) => {
            const v = m.values[yearIndex];
            const formatted =
              m.domain && m.domain[1] <= 1
                ? v.toFixed(2)
                : Number.isInteger(v)
                ? String(v)
                : v.toFixed(v >= 100 ? 1 : 2);
            return (
              <div
                key={m.id}
                className="bg-bg-deep/60 border border-line/60 rounded px-2 py-1.5"
              >
                <div className="text-[9px] text-muted truncate">{m.title}</div>
                <div
                  className="text-sm font-mono"
                  style={{ color: m.color }}
                >
                  {formatted}
                  {m.unit ? <span className="text-[9px] text-muted ml-1">{m.unit}</span> : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-widest text-muted mb-1">
          Bayesian verdict
        </div>
        <div className="space-y-1">
          {[
            { id: "H0", label: "same person", p: point.identity === "A" ? 0.72 : 0.21, color: "#22c55e" },
            { id: "H1", label: "double / mask", p: point.identity === "B" ? 0.62 : 0.12, color: "#ef4444" },
            { id: "H2", label: "different people", p: 0.16, color: "#f59e0b" },
          ].map((h) => (
            <div key={h.id} className="flex items-center gap-2">
              <span className="text-[10px] text-muted w-6">{h.id}</span>
              <div className="flex-1 h-2 bg-bg-deep rounded overflow-hidden">
                <div
                  className="h-full"
                  style={{ width: `${h.p * 100}%`, background: h.color }}
                />
              </div>
              <span className="text-[10px] font-mono w-10 text-right" style={{ color: h.color }}>
                {(h.p * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </aside>
  );
}
