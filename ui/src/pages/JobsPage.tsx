import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import Modal from "../components/common/Modal";
import { api, type Job } from "../api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [opened, setOpened] = useState<Job | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const list = await api.listJobs();
      if (!alive) return;
      setJobs(list);
      if (opened) {
        const refreshed = list.find((j) => j.id === opened.id);
        if (refreshed) setOpened(refreshed);
      }
    };
    tick();
    const t = setInterval(tick, 800);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [opened?.id]);

  async function addJob(kind: Job["kind"]) {
    const j = await api.startJob(kind);
    setJobs((prev) => [j, ...prev.filter((x) => x.id !== j.id)]);
  }

  return (
    <Page
      title="Jobs"
      subtitle="Asynchronous pipeline jobs · extract / recompute / calibrate / reindex"
      actions={
        <>
          <button onClick={() => addJob("extract")} className="px-3 h-8 rounded bg-ok/70 hover:bg-ok text-[11px] text-white">+ Extract</button>
          <button onClick={() => addJob("recompute_metrics")} className="px-3 h-8 rounded bg-info/70 hover:bg-info text-[11px] text-white">+ Recompute</button>
          <button onClick={() => addJob("calibrate")} className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">+ Calibrate</button>
          <button onClick={() => addJob("reindex")} className="px-3 h-8 rounded bg-line hover:bg-line/80 text-[11px] text-white">+ Reindex</button>
        </>
      }
    >
      <PanelCard title="Queue">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">id</th>
              <th className="text-left p-2">kind</th>
              <th className="text-left p-2">status</th>
              <th className="text-left p-2">progress</th>
              <th className="text-left p-2">processed</th>
              <th className="text-left p-2">started</th>
              <th className="text-left p-2">finished</th>
              <th className="text-left p-2">note</th>
              <th className="text-right p-2"></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id} className="border-b border-line/40">
                <td className="p-2 font-mono text-white">{j.id}</td>
                <td className="p-2 text-white">{j.kind}</td>
                <td className="p-2">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] ${
                      j.status === "done"
                        ? "bg-ok/30 text-ok"
                        : j.status === "running"
                        ? "bg-info/30 text-info"
                        : j.status === "failed"
                        ? "bg-danger/30 text-danger"
                        : "bg-muted/30 text-muted"
                    }`}
                  >
                    {j.status}
                  </span>
                </td>
                <td className="p-2 w-40">
                  <div className="h-1.5 bg-bg rounded overflow-hidden">
                    <div
                      className="h-full"
                      style={{
                        width: `${j.progress * 100}%`,
                        background:
                          j.status === "failed"
                            ? "#ef4444"
                            : j.status === "done"
                            ? "#22c55e"
                            : "#38bdf8",
                      }}
                    />
                  </div>
                  <div className="text-[9px] text-muted mt-0.5">{(j.progress * 100).toFixed(0)}%</div>
                </td>
                <td className="p-2 font-mono text-white">{j.processed}/{j.total}</td>
                <td className="p-2 text-muted">{j.startedAt}</td>
                <td className="p-2 text-muted">{j.finishedAt ?? "—"}</td>
                <td className="p-2 text-muted">{j.note ?? ""}</td>
                <td className="p-2 text-right">
                  <button
                    onClick={() => setOpened(j)}
                    className="px-2 h-6 rounded bg-line/60 hover:bg-line text-[10px] text-white"
                  >
                    Log
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>

      {opened && (
        <Modal title={`Job log — ${opened.id} (${opened.kind})`} onClose={() => setOpened(null)} width="max-w-4xl">
          <div className="grid grid-cols-4 gap-2 text-[11px] mb-3">
            <KV k="status" v={opened.status} />
            <KV k="progress" v={`${(opened.progress * 100).toFixed(0)}%`} />
            <KV k="processed" v={`${opened.processed}/${opened.total}`} />
            <KV k="started" v={opened.startedAt} />
          </div>
          <div className="bg-black/60 border border-line rounded p-2 max-h-[50vh] overflow-auto font-mono text-[11px] leading-relaxed">
            {(opened.logs ?? ["(no log entries)"]).map((ln, i) => (
              <div key={i} className={ln.includes("OOM") ? "text-danger" : ln.includes("complet") ? "text-ok" : "text-muted"}>
                {ln}
              </div>
            ))}
          </div>
        </Modal>
      )}
    </Page>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="bg-bg-deep/70 border border-line/60 rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-muted">{k}</div>
      <div className="text-sm font-mono text-white">{v}</div>
    </div>
  );
}
