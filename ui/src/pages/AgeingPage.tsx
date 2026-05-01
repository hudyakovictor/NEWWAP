import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type AgeingPoint } from "../api";

export default function AgeingPage() {
  const [data, setData] = useState<AgeingPoint[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getAgeingSeries().then((r) => {
      setData(r);
      setLoading(false);
    });
  }, []);

  if (loading) {
    return (
      <Page title="Ageing curve" subtitle="Loading…">
        <div className="text-[11px] text-muted">Fitting ageing model…</div>
      </Page>
    );
  }

  const years = data.map((p) => p.year);
  if (years.length === 0) {
    return (
      <Page title="Ageing curve" subtitle="No data">
        <div className="text-[11px] text-muted">No ageing data available.</div>
      </Page>
    );
  }
  const minY = Math.min(...data.map((p) => Math.min(p.observedAge, p.fittedAge))) - 1;
  const maxY = Math.max(...data.map((p) => Math.max(p.observedAge, p.fittedAge))) + 1;
  const W = 1200;
  const H = 360;
  const xDenom = Math.max(years.length - 1, 1);
  const px = (i: number) => (i / xDenom) * (W - 60) + 40;
  const py = (v: number) => H - 20 - ((v - minY) / (maxY - minY || 1)) * (H - 40);

  const fittedPath = data.map((p, i) => `${i === 0 ? "M" : "L"}${px(i)},${py(p.fittedAge)}`).join(" ");
  const observedPath = data.map((p, i) => `${i === 0 ? "M" : "L"}${px(i)},${py(p.observedAge)}`).join(" ");

  const outliers = data.filter((p) => p.outlier);

  return (
    <Page title="Ageing curve (debug)" subtitle="Observed vs fitted normal ageing with outlier detection">
      <PanelCard title="Timeline fit" className="mb-3">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-80 bg-bg-deep rounded">
          {/* gridlines */}
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <line
              key={t}
              x1={40}
              x2={W - 20}
              y1={20 + t * (H - 40)}
              y2={20 + t * (H - 40)}
              stroke="#1a2b44"
              strokeDasharray="2 3"
            />
          ))}
          {/* year ticks every 5 */}
          {years.map((y, i) =>
            y % 5 === 0 ? (
              <g key={y}>
                <line x1={px(i)} x2={px(i)} y1={H - 20} y2={H - 16} stroke="#233657" />
                <text x={px(i)} y={H - 6} fontSize={10} fill="#6b7a90" textAnchor="middle">{y}</text>
              </g>
            ) : null
          )}
          {/* axes */}
          <line x1={40} x2={W - 20} y1={H - 20} y2={H - 20} stroke="#233657" />
          <line x1={40} x2={40} y1={20} y2={H - 20} stroke="#233657" />
          {[minY, (minY + maxY) / 2, maxY].map((v, i) => (
            <text key={i} x={34} y={py(v) + 3} fontSize={10} fill="#6b7a90" textAnchor="end">
              {v.toFixed(0)}
            </text>
          ))}
          {/* fitted */}
          <path d={fittedPath} stroke="#38bdf8" strokeWidth={2} fill="none" strokeDasharray="4 4" />
          {/* observed */}
          <path d={observedPath} stroke="#22c55e" strokeWidth={2} fill="none" />
          {/* points */}
          {data.map((p, i) => (
            <g key={p.year}>
              <circle
                cx={px(i)}
                cy={py(p.observedAge)}
                r={p.outlier ? 5 : 3}
                fill={p.outlier ? "#ef4444" : "#22c55e"}
                stroke={p.outlier ? "#fff" : "none"}
              >
                <title>
                  {p.year}: observed {p.observedAge}, fitted {p.fittedAge}, residual {p.residual}
                </title>
              </circle>
              {p.outlier && (
                <text x={px(i)} y={py(p.observedAge) - 8} fontSize={9} fill="#ef4444" textAnchor="middle">
                  Δ{p.residual > 0 ? "+" : ""}{p.residual}
                </text>
              )}
            </g>
          ))}
          {/* legend */}
          <g transform={`translate(${W - 220}, 30)`}>
            <rect x={-6} y={-14} width={210} height={46} fill="#0a1523" stroke="#233657" rx={4} />
            <line x1={0} x2={26} y1={0} y2={0} stroke="#38bdf8" strokeDasharray="4 4" strokeWidth={2} />
            <text x={32} y={3} fontSize={10} fill="#cfd8e6">fitted normal ageing</text>
            <line x1={0} x2={26} y1={18} y2={18} stroke="#22c55e" strokeWidth={2} />
            <text x={32} y={21} fontSize={10} fill="#cfd8e6">observed</text>
            <circle cx={132} cy={18} r={4} fill="#ef4444" stroke="#fff" />
            <text x={142} y={21} fontSize={10} fill="#cfd8e6">outlier</text>
          </g>
        </svg>
      </PanelCard>

      <div className="grid grid-cols-3 gap-3">
        <PanelCard title="Outlier summary">
          <div className="text-2xl font-semibold text-danger">{outliers.length}</div>
          <div className="text-[11px] text-muted">years out of {data.length} exceed 2σ threshold</div>
        </PanelCard>
        <PanelCard title="Max residual">
          <div className="text-2xl font-semibold text-warn">
            {Math.max(...data.map((p) => Math.abs(p.residual))).toFixed(2)}
          </div>
          <div className="text-[11px] text-muted">largest deviation from fitted ageing</div>
        </PanelCard>
        <PanelCard title="Fitted rate">
          <div className="text-2xl font-semibold text-info">1.00 yr/yr</div>
          <div className="text-[11px] text-muted">linear ageing assumption (debug)</div>
        </PanelCard>
      </div>

      <PanelCard title={`Outliers (${outliers.length})`} className="mt-3">
        {outliers.length === 0 ? (
          <div className="text-[11px] text-ok">No outliers — ageing is within normal bounds.</div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-2">year</th>
                <th className="text-left p-2">observed</th>
                <th className="text-left p-2">fitted</th>
                <th className="text-left p-2">residual</th>
                <th className="text-left p-2">note</th>
              </tr>
            </thead>
            <tbody>
              {outliers.map((p) => (
                <tr key={p.year} className="border-b border-line/40">
                  <td className="p-2 font-mono text-white">{p.year}</td>
                  <td className="p-2 font-mono text-warn">{p.observedAge}</td>
                  <td className="p-2 font-mono text-info">{p.fittedAge}</td>
                  <td className="p-2 font-mono text-danger">{p.residual}</td>
                  <td className="p-2 text-muted">{p.note ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PanelCard>

      <PanelCard title="All points" className="mt-3">
        <div className="overflow-auto">
          <table className="w-full text-[11px]">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-2">year</th>
                <th className="text-left p-2">observed</th>
                <th className="text-left p-2">fitted</th>
                <th className="text-left p-2">residual</th>
                <th className="text-left p-2">outlier</th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.year} className={`border-b border-line/30 ${p.outlier ? "bg-danger/10" : ""}`}>
                  <td className="p-2 font-mono text-white">{p.year}</td>
                  <td className="p-2 font-mono text-white">{p.observedAge}</td>
                  <td className="p-2 font-mono text-muted">{p.fittedAge}</td>
                  <td className={`p-2 font-mono ${Math.abs(p.residual) > 2 ? "text-danger" : "text-muted"}`}>
                    {p.residual}
                  </td>
                  <td className="p-2">{p.outlier ? <span className="text-danger">✓</span> : <span className="text-muted">—</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PanelCard>
    </Page>
  );
}
