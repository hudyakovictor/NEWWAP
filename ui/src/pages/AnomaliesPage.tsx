import { useEffect, useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type AnomalyRecord } from "../api";
import { useApp } from "../store/appStore";

const KINDS = ["any", "chronology", "synthetic", "pose", "cluster", "calibration"] as const;
const SEVS = ["any", "ok", "info", "warn", "danger"] as const;

export default function AnomaliesPage() {
  const [items, setItems] = useState<AnomalyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState<(typeof KINDS)[number]>("any");
  const [sev, setSev] = useState<(typeof SEVS)[number]>("any");
  const [hideResolved, setHideResolved] = useState(true);
  const [query, setQuery] = useState("");
  const { setPage } = useApp();

  useEffect(() => {
    api.listAnomalies().then((r) => {
      setItems(r);
      setLoading(false);
    });
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((a) => {
      if (kind !== "any" && a.kind !== kind) return false;
      if (sev !== "any" && a.severity !== sev) return false;
      if (hideResolved && a.resolved) return false;
      if (q && !a.title.toLowerCase().includes(q) && !String(a.year).includes(q)) return false;
      return true;
    });
  }, [items, kind, sev, hideResolved, query]);

  const counts = useMemo(() => {
    return {
      total: items.length,
      danger: items.filter((i) => i.severity === "danger" && !i.resolved).length,
      warn: items.filter((i) => i.severity === "warn" && !i.resolved).length,
      info: items.filter((i) => i.severity === "info" && !i.resolved).length,
      resolved: items.filter((i) => i.resolved).length,
    };
  }, [items]);

  return (
    <Page
      title="Anomalies registry"
      subtitle="All flags raised by chronology, synthetic-material, pose, and calibration checks"
      actions={
        <>
          <button
            onClick={() => setPage("timeline")}
            className="px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white"
          >
            ← Back to timeline
          </button>
          <button className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">
            Export JSON
          </button>
        </>
      }
    >

      <div className="grid grid-cols-5 gap-3 mb-3">
        <Stat label="Total" value={counts.total} color="#cfd8e6" />
        <Stat label="Danger" value={counts.danger} color="#ef4444" />
        <Stat label="Warn" value={counts.warn} color="#f59e0b" />
        <Stat label="Info" value={counts.info} color="#38bdf8" />
        <Stat label="Resolved" value={counts.resolved} color="#22c55e" />
      </div>

      <PanelCard title="Filters" className="mb-3">
        <div className="grid grid-cols-5 gap-2 text-[11px]">
          <label className="flex flex-col gap-1">
            <span className="text-muted">Search</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="h-8 px-2 rounded bg-bg-deep border border-line text-white"
              placeholder="year or text"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-muted">Kind</span>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as any)}
              className="h-8 px-2 rounded bg-bg-deep border border-line text-white"
            >
              {KINDS.map((k) => <option key={k}>{k}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-muted">Severity</span>
            <select
              value={sev}
              onChange={(e) => setSev(e.target.value as any)}
              className="h-8 px-2 rounded bg-bg-deep border border-line text-white"
            >
              {SEVS.map((k) => <option key={k}>{k}</option>)}
            </select>
          </label>
          <label className="flex items-end gap-2 cursor-pointer text-white">
            <input
              type="checkbox"
              checked={hideResolved}
              onChange={(e) => setHideResolved(e.target.checked)}
            />
            Hide resolved
          </label>
        </div>
      </PanelCard>

      <PanelCard title={`${filtered.length} anomalies`}>
        {loading ? (
          <div className="text-[11px] text-muted">Loading…</div>
        ) : (
          <table className="w-full text-[11px]">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-2">severity</th>
                <th className="text-left p-2">kind</th>
                <th className="text-left p-2">year</th>
                <th className="text-left p-2">photo</th>
                <th className="text-left p-2">title</th>
                <th className="text-left p-2">detected</th>
                <th className="text-left p-2">status</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((a) => (
                <tr key={a.id} className="border-b border-line/30 hover:bg-line/20">
                  <td className="p-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] ${
                        a.severity === "danger"
                          ? "bg-danger/30 text-danger"
                          : a.severity === "warn"
                          ? "bg-warn/30 text-warn"
                          : a.severity === "info"
                          ? "bg-info/30 text-info"
                          : "bg-ok/30 text-ok"
                      }`}
                    >
                      {a.severity}
                    </span>
                  </td>
                  <td className="p-2 text-white">{a.kind}</td>
                  <td className="p-2 font-mono text-white">{a.year}</td>
                  <td className="p-2 font-mono text-muted">{a.photoId ?? "—"}</td>
                  <td className="p-2 text-white">{a.title}</td>
                  <td className="p-2 text-muted">{a.detectedAt}</td>
                  <td className="p-2">
                    <span className={a.resolved ? "text-ok" : "text-muted"}>
                      {a.resolved ? "resolved" : "open"}
                    </span>
                  </td>
                  <td className="p-2 text-right">
                    <button
                      onClick={() =>
                        setItems((prev) =>
                          prev.map((x) => (x.id === a.id ? { ...x, resolved: !x.resolved } : x))
                        )
                      }
                      className="px-2 h-6 rounded bg-line/60 hover:bg-line text-[10px] text-white"
                    >
                      {a.resolved ? "reopen" : "resolve"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PanelCard>
    </Page>
  );
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <PanelCard>
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </PanelCard>
  );
}
