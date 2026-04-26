import { useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { buildIterations, type Iteration, type PhotoCompare } from "../data/iterationPlan";
import type { RealPhoto } from "../data/photoRegistry";
import { useApp } from "../store/appStore";

/**
 * Iteration analysis: each iteration is a 4-photo set
 * (calibration pair + main early/late) + their comparison metrics.
 *
 * The user advances through a deterministic schedule of year pairs
 * (extremes first, then binary subdivision) and inspects how the main
 * pair's delta compares against the calibration baseline.
 */

export default function IterationsPage() {
  const ITERATIONS = useMemo(() => buildIterations(1999, 2025), []);
  const [idx, setIdx] = useState(0);
  const it = ITERATIONS[idx];
  const { setPairA, setPairB, setPage } = useApp();

  if (!it || !it.calib) {
    return (
      <Page title="Iterations">
        <div className="text-[11px] text-muted">Could not pick a calibration pair.</div>
      </Page>
    );
  }

  return (
    <Page
      title={`Iteration #${it.index} of ${ITERATIONS.length}  ·  (${it.earlyYear}, ${it.lateYear})`}
      subtitle="Each step pairs an analysis pair with a calibration baseline. Compare divergence against baseline to assess identity stability."
      actions={
        <>
          <button
            onClick={() => setIdx(Math.max(0, idx - 1))}
            disabled={idx === 0}
            className="px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white disabled:opacity-40"
          >
            ← Previous
          </button>
          <button
            onClick={() => setIdx(Math.min(ITERATIONS.length - 1, idx + 1))}
            disabled={idx === ITERATIONS.length - 1}
            className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white disabled:opacity-40"
          >
            Next iteration →
          </button>
        </>
      }
    >
      <div className="grid grid-cols-2 gap-3 mb-3">
        <PanelCard title={`Calibration pair (myface, baseline = same person)`}>
          <PhotoPair a={it.calib.a} b={it.calib.b} />
          <div className="mt-2 text-[11px] text-muted">
            This pair is the same subject. Treat its delta as "noise floor".
          </div>
        </PanelCard>
        <PanelCard
          title={`Analysis pair (main: ${it.earlyYear} → ${it.lateYear})`}
        >
          {it.early && it.late ? (
            <PhotoPair a={it.early} b={it.late} />
          ) : (
            <div className="text-[11px] text-warn">
              Missing photo for {!it.early ? it.earlyYear : it.lateYear}.
            </div>
          )}
          {it.early && it.late && (
            <div className="mt-2 flex gap-2">
              <button
                onClick={() => {
                  setPairA(`main-${it.early!.file}`);
                  setPairB(`main-${it.late!.file}`);
                  setPage("pairs");
                }}
                className="px-2 h-6 rounded bg-info/70 hover:bg-info text-[10px] text-white"
              >
                Open in Pair analysis
              </button>
            </div>
          )}
        </PanelCard>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-3">
        <DeltaCard title="Calibration Δ (baseline)" data={it.calibDelta} accent="#22c55e" />
        <DeltaCard title="Main Δ (analysis)" data={it.mainDelta} accent="#38bdf8" />
        <DeltaCard
          title="Divergence  (|main − baseline|)"
          data={it.divergence}
          accent="#f59e0b"
          isDivergence
        />
      </div>

      <PanelCard title={`All iterations (${ITERATIONS.length})`} className="mb-3">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-1">#</th>
              <th className="text-left p-1">years</th>
              <th className="text-left p-1">main Δyaw</th>
              <th className="text-left p-1">main Δlum</th>
              <th className="text-left p-1">divergence Δyaw</th>
              <th className="text-left p-1">divergence Δlum</th>
              <th className="text-left p-1">flag</th>
              <th className="text-right p-1"></th>
            </tr>
          </thead>
          <tbody>
            {ITERATIONS.map((row, i) => {
              const flagged =
                (row.divergence.luminanceDelta ?? 0) > 30 ||
                (row.divergence.poseDeltaYaw ?? 0) > 5;
              return (
                <tr
                  key={i}
                  onClick={() => setIdx(i)}
                  className={`border-b border-line/30 cursor-pointer hover:bg-line/40 ${
                    i === idx ? "bg-line/60" : ""
                  } ${flagged ? "bg-warn/10" : ""}`}
                >
                  <td className="p-1 font-mono text-white">{row.index}</td>
                  <td className="p-1 font-mono text-muted">{row.earlyYear} → {row.lateYear}</td>
                  <td className="p-1 font-mono">{fmtNum(row.mainDelta.poseDeltaYaw, "°")}</td>
                  <td className="p-1 font-mono">{fmtNum(row.mainDelta.luminanceDelta, "")}</td>
                  <td className="p-1 font-mono text-warn">{fmtNum(row.divergence.poseDeltaYaw, "°")}</td>
                  <td className="p-1 font-mono text-warn">{fmtNum(row.divergence.luminanceDelta, "")}</td>
                  <td className="p-1">
                    {flagged ? <span className="text-warn">⚠</span> : <span className="text-ok">✓</span>}
                  </td>
                  <td className="p-1 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setIdx(i);
                      }}
                      className="px-2 h-5 rounded bg-line/60 hover:bg-line text-[10px] text-white"
                    >
                      open
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </PanelCard>
    </Page>
  );
}

function PhotoPair({ a, b }: { a: RealPhoto; b: RealPhoto }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <PhotoCell rp={a} />
      <PhotoCell rp={b} />
    </div>
  );
}

function PhotoCell({ rp }: { rp: RealPhoto }) {
  return (
    <div className="bg-bg-deep rounded border border-line/60 overflow-hidden">
      <img src={rp.url} alt={rp.file} className="w-full aspect-square object-cover" />
      <div className="p-1 text-[10px]">
        <div className="text-white font-mono truncate">{rp.file}</div>
        <div className="text-muted">
          {rp.date ?? "no-date"} · {rp.pose.classification}
        </div>
        <div className="text-info font-mono">
          yaw {rp.pose.yaw?.toFixed(1) ?? "—"}° · pitch {rp.pose.pitch?.toFixed(1) ?? "—"}°
        </div>
        {rp.faceStats && (
          <div className="text-muted">
            lum {rp.faceStats.meanLum.toFixed(0)} · σ {rp.faceStats.stdLum.toFixed(0)}
          </div>
        )}
      </div>
    </div>
  );
}

function DeltaCard({
  title,
  data,
  accent,
  isDivergence = false,
}: {
  title: string;
  data: PhotoCompare;
  accent: string;
  isDivergence?: boolean;
}) {
  const rows: { label: string; value: number | null; unit?: string; warn?: boolean }[] = [
    { label: "Δ yaw",        value: data.poseDeltaYaw,    unit: "°", warn: isDivergence && Math.abs(data.poseDeltaYaw ?? 0) > 5 },
    { label: "Δ pitch",      value: data.poseDeltaPitch,  unit: "°" },
    { label: "Δ roll",       value: data.poseDeltaRoll,   unit: "°" },
    { label: "Δ luminance",  value: data.luminanceDelta,  warn: isDivergence && Math.abs(data.luminanceDelta ?? 0) > 30 },
    { label: "Δ red",        value: data.redDelta },
    { label: "Δ green",      value: data.greenDelta },
    { label: "Δ blue",       value: data.blueDelta },
  ];
  return (
    <PanelCard>
      <div className="text-[11px] uppercase tracking-widest mb-2" style={{ color: accent }}>
        {title}
      </div>
      <div className="space-y-1">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between text-[11px] border-b border-line/40 py-0.5">
            <span className="text-muted">{r.label}</span>
            <span className={`font-mono ${r.warn ? "text-warn font-semibold" : "text-white"}`}>
              {fmtNum(r.value, r.unit ?? "")}
            </span>
          </div>
        ))}
      </div>
    </PanelCard>
  );
}

function fmtNum(v: number | null, unit: string): string {
  if (v == null) return "—";
  return `${v}${unit}`;
}
