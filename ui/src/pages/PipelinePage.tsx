import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type PipelineStage } from "../api";

export default function PipelinePage() {
  const [stages, setStages] = useState<PipelineStage[]>([]);

  useEffect(() => {
    api.getPipelineStages().then(setStages);
  }, []);

  if (!stages.length) {
    return <Page title="Pipeline diagnostics"><div className="text-[11px] text-muted">Loading…</div></Page>;
  }

  const totalFailed = stages.reduce((a, s) => a + s.failed, 0);
  const totalTime = stages.reduce((a, s) => a + s.avgMs, 0);
  const maxGPU = Math.max(...stages.map((s) => s.gpuMemoryMB ?? 0));

  return (
    <Page
      title="Pipeline diagnostics (debug)"
      subtitle="Per-stage ingest pipeline: throughput, errors, GPU footprint"
      actions={
        <button className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">
          Re-run failed items
        </button>
      }
    >
      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="stages" value={String(stages.length)} color="#38bdf8" />
        <Stat label="total failed" value={String(totalFailed)} color={totalFailed > 0 ? "#ef4444" : "#22c55e"} />
        <Stat label="avg total per item" value={`${totalTime} ms`} color="#a855f7" />
        <Stat label="peak GPU" value={`${maxGPU} MB`} color="#22c55e" />
      </div>

      <PanelCard title="Stage flow" className="mb-3">
        <div className="flex gap-2 overflow-auto pb-2">
          {stages.map((s, i) => {
            const dropPct =
              i === 0
                ? 0
                : ((stages[i - 1].outputCount - s.outputCount) / (stages[i - 1].outputCount || 1)) * 100;
            return (
              <div key={s.id} className="flex items-center gap-2 shrink-0">
                <div
                  className={`w-48 rounded border p-2 ${
                    s.failed > 0 ? "border-warn/70 bg-warn/10" : "border-line bg-bg-deep"
                  }`}
                >
                  <div className="text-[10px] text-muted">#{s.order}</div>
                  <div className="text-[12px] font-semibold text-white leading-tight">{s.name}</div>
                  <div className="mt-1 grid grid-cols-2 gap-1 text-[10px]">
                    <div className="text-muted">in</div>
                    <div className="font-mono text-white">{s.inputCount}</div>
                    <div className="text-muted">out</div>
                    <div className="font-mono text-white">{s.outputCount}</div>
                    <div className="text-muted">fail</div>
                    <div className={`font-mono ${s.failed > 0 ? "text-danger" : "text-muted"}`}>{s.failed}</div>
                    <div className="text-muted">avg</div>
                    <div className="font-mono text-info">{s.avgMs} ms</div>
                    {s.gpuMemoryMB ? (
                      <>
                        <div className="text-muted">gpu</div>
                        <div className="font-mono text-accent">{s.gpuMemoryMB} MB</div>
                      </>
                    ) : null}
                  </div>
                </div>
                {i < stages.length - 1 && (
                  <div className="flex flex-col items-center text-[10px]">
                    <span className={dropPct > 0 ? "text-warn" : "text-muted"}>
                      {dropPct > 0 ? `−${dropPct.toFixed(1)}%` : "→"}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </PanelCard>

      <PanelCard title="Details">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">#</th>
              <th className="text-left p-2">stage</th>
              <th className="text-left p-2">in</th>
              <th className="text-left p-2">out</th>
              <th className="text-left p-2">failed</th>
              <th className="text-left p-2">avg ms</th>
              <th className="text-left p-2">GPU MB</th>
              <th className="text-left p-2">last error</th>
              <th className="text-left p-2">notes</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((s) => (
              <tr key={s.id} className="border-b border-line/40">
                <td className="p-2 text-muted">{s.order}</td>
                <td className="p-2 text-white">{s.name}</td>
                <td className="p-2 font-mono text-white">{s.inputCount}</td>
                <td className="p-2 font-mono text-white">{s.outputCount}</td>
                <td className={`p-2 font-mono ${s.failed > 0 ? "text-danger" : "text-muted"}`}>{s.failed}</td>
                <td className="p-2 font-mono text-info">{s.avgMs}</td>
                <td className="p-2 font-mono text-accent">{s.gpuMemoryMB ?? "—"}</td>
                <td className="p-2 text-warn">{s.lastError ?? ""}</td>
                <td className="p-2 text-muted">{s.notes ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>
    </Page>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <PanelCard>
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </PanelCard>
  );
}
