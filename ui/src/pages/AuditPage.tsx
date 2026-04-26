import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { runAudit, type AuditReport } from "../debug/audit";
import { api } from "../api";
import { getAllLogs } from "../debug/logger";
import { getHistory, clearHistory, type AuditSnapshot } from "../debug/auditHistory";

export default function AuditPage() {
  const [report, setReport] = useState<AuditReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<AuditSnapshot[]>(getHistory());

  async function refresh() {
    setBusy(true);
    const r = await runAudit(api);
    setReport(r);
    (window as any).deeputin.lastAudit = r;
    setHistory(getHistory());
    setBusy(false);
  }

  useEffect(() => {
    refresh();
  }, []);

  if (!report) {
    return (
      <Page title="Audit">
        <div className="text-[11px] text-muted">Running invariants…</div>
      </Page>
    );
  }

  const sevColor = (s: string) =>
    s === "danger" ? "#ef4444" : s === "warn" ? "#f59e0b" : "#38bdf8";

  const snapshot = () => {
    const payload = {
      audit: report,
      logs: getAllLogs(),
      at: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `deeputin-session-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Page
      title="Audit (autonomous)"
      subtitle={`Generated ${report.generatedAt} · ${report.durationMs}ms · ${report.environment.runtime}`}
      actions={
        <>
          <button
            onClick={refresh}
            disabled={busy}
            className="px-3 h-8 rounded bg-ok/70 hover:bg-ok text-[11px] text-white disabled:opacity-40"
          >
            {busy ? "Running…" : "Re-run audit"}
          </button>
          <button
            onClick={snapshot}
            className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white"
          >
            Download session snapshot
          </button>
          <button
            onClick={() => {
              navigator.clipboard.writeText(JSON.stringify(report, null, 2));
            }}
            className="px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white"
          >
            Copy report JSON
          </button>
        </>
      }
    >
      {/* Summary */}
      <PanelCard title="Summary" className="mb-3">
        <pre className="text-[12px] whitespace-pre-wrap text-white font-mono">{report.summary}</pre>
      </PanelCard>

      {/* Counters */}
      <div className="grid grid-cols-5 gap-2 mb-3">
        <Stat label="findings"   value={report.counts.total}  color="#cfd8e6" />
        <Stat label="danger"     value={report.counts.danger} color="#ef4444" />
        <Stat label="warn"       value={report.counts.warn}   color="#f59e0b" />
        <Stat label="info"       value={report.counts.info}   color="#38bdf8" />
        <Stat label="endpoints"  value={`${report.endpoints.filter((e) => e.status === "ok").length}/${report.endpoints.length}`} color={report.endpoints.every((e) => e.status === "ok") ? "#22c55e" : "#ef4444"} />
      </div>

      {/* Endpoints */}
      <PanelCard title="Endpoints" className="mb-3">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">endpoint</th>
              <th className="text-left p-2">status</th>
              <th className="text-left p-2">ms</th>
              <th className="text-left p-2">note</th>
            </tr>
          </thead>
          <tbody>
            {report.endpoints.map((e) => (
              <tr key={e.name} className="border-b border-line/40">
                <td className="p-2 font-mono text-white">{e.name}</td>
                <td className="p-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] ${
                      e.status === "ok" ? "bg-ok/30 text-ok" : "bg-danger/30 text-danger"
                    }`}
                  >
                    {e.status}
                  </span>
                </td>
                <td className="p-2 font-mono text-info">{e.ms}</td>
                <td className="p-2 text-warn">{e.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>

      {/* Findings */}
      <PanelCard title={`Findings (${report.findings.length})`} className="mb-3">
        {report.findings.length === 0 ? (
          <div className="text-[11px] text-ok">All invariants pass. Nothing to investigate.</div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-2">sev</th>
                <th className="text-left p-2">area</th>
                <th className="text-left p-2">id</th>
                <th className="text-left p-2">message</th>
                <th className="text-left p-2">expected</th>
                <th className="text-left p-2">actual</th>
                <th className="text-left p-2">hint</th>
              </tr>
            </thead>
            <tbody>
              {report.findings.map((f) => (
                <tr key={f.id} className="border-b border-line/30">
                  <td className="p-2">
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px]"
                      style={{ background: sevColor(f.severity) + "30", color: sevColor(f.severity) }}
                    >
                      {f.severity}
                    </span>
                  </td>
                  <td className="p-2 text-accent">{f.area}</td>
                  <td className="p-2 font-mono text-white truncate max-w-[200px]">{f.id}</td>
                  <td className="p-2 text-white">{f.message}</td>
                  <td className="p-2 text-muted">{f.expected ?? ""}</td>
                  <td className="p-2 text-warn font-mono">{f.actual !== undefined ? JSON.stringify(f.actual) : ""}</td>
                  <td className="p-2 text-muted">{f.hint ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PanelCard>

      {/* Timings */}
      <PanelCard title="Invariant timings" className="mb-3">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">invariant</th>
              <th className="text-left p-2">ms</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(report.timings).map(([k, v]) => (
              <tr key={k} className="border-b border-line/30">
                <td className="p-2 font-mono text-white">{k}</td>
                <td className="p-2 font-mono text-info">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>

      {/* History */}
      {history.length > 1 && (
        <PanelCard
          title={`Audit history (${history.length} runs)`}
          className="mb-3"
          actions={
            <button
              onClick={() => {
                clearHistory();
                setHistory([]);
              }}
              className="px-2 h-6 rounded bg-line text-[10px] text-white"
            >
              clear
            </button>
          }
        >
          <HistoryStrip history={history} />
          <table className="w-full text-[11px] mt-3">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-2">at</th>
                <th className="text-left p-2">total</th>
                <th className="text-left p-2">danger</th>
                <th className="text-left p-2">warn</th>
                <th className="text-left p-2">info</th>
                <th className="text-left p-2">endpoints</th>
                <th className="text-left p-2">ms</th>
                <th className="text-left p-2">Δ vs prev</th>
              </tr>
            </thead>
            <tbody>
              {history.slice().reverse().map((s, i, arr) => {
                const prev = arr[i + 1];
                const delta = prev ? s.total - prev.total : 0;
                return (
                  <tr key={s.at} className="border-b border-line/30">
                    <td className="p-2 font-mono text-muted">{s.at.replace("T", " ").slice(0, 19)}</td>
                    <td className="p-2 font-mono text-white">{s.total}</td>
                    <td className="p-2 font-mono text-danger">{s.danger}</td>
                    <td className="p-2 font-mono text-warn">{s.warn}</td>
                    <td className="p-2 font-mono text-info">{s.info}</td>
                    <td className="p-2 font-mono text-white">{s.endpointsOk}/{s.endpointsTotal}</td>
                    <td className="p-2 font-mono text-muted">{s.durationMs}</td>
                    <td className={`p-2 font-mono ${delta > 0 ? "text-danger" : delta < 0 ? "text-ok" : "text-muted"}`}>
                      {delta > 0 ? `+${delta}` : delta < 0 ? `${delta}` : "·"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </PanelCard>
      )}

      {/* TZ coverage */}
      <PanelCard title={`TZ coverage (${report.tzCoverage.length} topics)`}>
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">topic</th>
              <th className="text-left p-2">implementation</th>
            </tr>
          </thead>
          <tbody>
            {report.tzCoverage.map((t) => (
              <tr key={t.topic} className="border-b border-line/30">
                <td className="p-2 text-white">{t.topic}</td>
                <td className="p-2 font-mono text-muted">{t.impl}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>
    </Page>
  );
}

function HistoryStrip({ history }: { history: AuditSnapshot[] }) {
  // Sparkline-ish: tiny stacked bars showing total, broken into danger/warn/info.
  const max = Math.max(1, ...history.map((s) => s.total));
  return (
    <div className="flex items-end gap-1 h-16">
      {history.slice(-50).map((s, i) => {
        const total = s.total || 0;
        const h = (total / max) * 100;
        return (
          <div
            key={s.at + i}
            className="flex-1 flex flex-col-reverse min-w-[3px]"
            title={`${s.at}\ntotal ${s.total} (d=${s.danger} w=${s.warn} i=${s.info})\nsummary: ${s.summary.replace(/\n/g, " · ")}`}
          >
            {total === 0 ? (
              <div style={{ height: "4px", background: "#22c55e", opacity: 0.6 }} />
            ) : (
              <div className="flex flex-col-reverse w-full" style={{ height: `${h}%` }}>
                <div style={{ flex: s.info, background: "#38bdf8" }} />
                <div style={{ flex: s.warn, background: "#f59e0b" }} />
                <div style={{ flex: s.danger, background: "#ef4444" }} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: React.ReactNode; color: string }) {
  return (
    <div className="bg-bg-panel border border-line rounded p-2">
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}
