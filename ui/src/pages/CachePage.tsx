import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type CacheSummary } from "../api";

export default function CachePage() {
  const [s, setS] = useState<CacheSummary | null>(null);

  useEffect(() => {
    api.getCacheSummary().then(setS);
  }, []);

  if (!s) return <Page title="Reconstruction cache"><div className="text-[11px] text-muted">Loading…</div></Page>;

  const budgetUsage = s.vramFootprintMB / s.vramBudgetMB;

  return (
    <Page
      title="Reconstruction cache (debug)"
      subtitle="MD5-keyed cache of 3DDFA_v3 reconstructions · VRAM-aware eviction"
      actions={
        <>
          <button className="px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white">Flush all</button>
          <button className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">Prewarm timeline</button>
        </>
      }
    >
      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="entries" value={`${s.currentSize}/${s.maxSize}`} color="#38bdf8" />
        <Stat label="VRAM used" value={`${s.vramFootprintMB} MB`} color="#a855f7" />
        <Stat label="VRAM budget" value={`${s.vramBudgetMB} MB`} color="#22c55e" />
        <Stat label="utilization" value={`${(budgetUsage * 100).toFixed(1)}%`} color={budgetUsage > 0.8 ? "#ef4444" : "#22c55e"} />
      </div>

      <PanelCard title="VRAM budget" className="mb-3">
        <div className="h-3 bg-bg-deep rounded overflow-hidden">
          <div
            className="h-full"
            style={{
              width: `${Math.min(100, budgetUsage * 100)}%`,
              background: budgetUsage > 0.8 ? "#ef4444" : budgetUsage > 0.6 ? "#f59e0b" : "#22c55e",
            }}
          />
        </div>
        <div className="text-[11px] text-muted mt-2">
          Cache has explicit VRAM-free on eviction. Guard blocks new reconstructions if headroom drops below ~200 MB.
        </div>
      </PanelCard>

      <PanelCard title={`Entries (${s.entries.length})`} className="mb-3">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">md5</th>
              <th className="text-left p-2">photo</th>
              <th className="text-left p-2">year</th>
              <th className="text-left p-2">neutral</th>
              <th className="text-left p-2">VRAM</th>
              <th className="text-left p-2">created</th>
              <th className="text-left p-2">last access</th>
              <th className="text-left p-2">hits</th>
              <th className="text-right p-2"></th>
            </tr>
          </thead>
          <tbody>
            {s.entries.map((e) => (
              <tr key={e.md5} className="border-b border-line/30">
                <td className="p-2 font-mono text-white truncate max-w-[200px]">{e.md5}</td>
                <td className="p-2 font-mono text-muted">{e.photoId}</td>
                <td className="p-2 font-mono text-white">{e.year}</td>
                <td className="p-2">{e.neutral ? <span className="text-ok">yes</span> : <span className="text-muted">no</span>}</td>
                <td className="p-2 font-mono text-white">{e.vramMB} MB</td>
                <td className="p-2 text-muted">{e.createdAt}</td>
                <td className="p-2 text-muted">{e.lastAccess}</td>
                <td className="p-2 font-mono text-info">{e.hits}</td>
                <td className="p-2 text-right">
                  <button className="px-2 h-6 rounded bg-danger/40 hover:bg-danger/70 text-[10px] text-white">
                    evict
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>

      <PanelCard title="Eviction history">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">md5</th>
              <th className="text-left p-2">when</th>
              <th className="text-left p-2">reason</th>
            </tr>
          </thead>
          <tbody>
            {s.evictions.map((ev, i) => (
              <tr key={i} className="border-b border-line/30">
                <td className="p-2 font-mono text-muted">{ev.md5}</td>
                <td className="p-2 text-muted">{ev.at}</td>
                <td className={`p-2 ${ev.reason.includes("VRAM") ? "text-warn" : "text-muted"}`}>{ev.reason}</td>
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
