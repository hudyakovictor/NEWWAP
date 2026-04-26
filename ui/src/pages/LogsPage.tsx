import { useEffect, useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import {
  getAllLogs,
  subscribe,
  clearLogs,
  type LogEntry,
  type LogCategory,
  type LogLevel,
} from "../debug/logger";
import { runSelfTest } from "../debug/selfTest";

const CATEGORIES: (LogCategory | "all")[] = [
  "all", "boot", "api", "nav", "ui", "pipeline", "bayes",
  "calibration", "cache", "ageing", "pair", "photo", "validation", "self_test",
];
const LEVELS: (LogLevel | "all")[] = ["all", "trace", "debug", "info", "warn", "error"];

const LEVEL_COLOR: Record<LogLevel, string> = {
  trace: "#6b7a90",
  debug: "#38bdf8",
  info:  "#22c55e",
  warn:  "#f59e0b",
  error: "#ef4444",
};

export default function LogsPage() {
  const [items, setItems] = useState<LogEntry[]>(getAllLogs());
  const [category, setCategory] = useState<(LogCategory | "all")>("all");
  const [level, setLevel] = useState<(LogLevel | "all")>("all");
  const [onlySuspicious, setOnlySuspicious] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<LogEntry | null>(null);
  const [follow, setFollow] = useState(true);

  useEffect(() => {
    const unsub = subscribe(() => {
      setItems(getAllLogs().slice());
    });
    return () => {
      unsub();
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((e) => {
      if (category !== "all" && e.category !== category) return false;
      if (level !== "all" && e.level !== level) return false;
      if (onlySuspicious && !e.suspicious) return false;
      if (q) {
        const hay = `${e.scope} ${e.message} ${e.category}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [items, category, level, onlySuspicious, query]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {
      total: items.length,
      suspicious: 0,
      error: 0,
      warn: 0,
      info: 0,
      debug: 0,
      trace: 0,
    };
    items.forEach((e) => {
      if (e.suspicious) c.suspicious++;
      c[e.level]++;
    });
    return c;
  }, [items]);

  function exportJson() {
    const blob = new Blob([JSON.stringify(items, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `deeputin-logs-${new Date().toISOString().slice(0, 19)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <Page
      title="Logs (notebook stream)"
      subtitle="Every pipeline event, API call, navigation and validation check in order"
      actions={
        <>
          <button
            onClick={() => runSelfTest()}
            className="px-3 h-8 rounded bg-ok/70 hover:bg-ok text-[11px] text-white"
          >
            Re-run self-test
          </button>
          <button
            onClick={exportJson}
            className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white"
          >
            Export JSON
          </button>
          <button
            onClick={() => {
              clearLogs();
              setItems([]);
            }}
            className="px-3 h-8 rounded bg-danger/60 hover:bg-danger text-[11px] text-white"
          >
            Clear
          </button>
        </>
      }
    >
      {/* Counters */}
      <div className="grid grid-cols-7 gap-2 mb-3">
        <Stat label="total"       value={counts.total}      color="#cfd8e6" />
        <Stat label="suspicious"  value={counts.suspicious} color="#ef4444" />
        <Stat label="error"       value={counts.error}      color={LEVEL_COLOR.error} />
        <Stat label="warn"        value={counts.warn}       color={LEVEL_COLOR.warn} />
        <Stat label="info"        value={counts.info}       color={LEVEL_COLOR.info} />
        <Stat label="debug"       value={counts.debug}      color={LEVEL_COLOR.debug} />
        <Stat label="trace"       value={counts.trace}      color={LEVEL_COLOR.trace} />
      </div>

      {/* Filters */}
      <PanelCard title="Filters" className="mb-3">
        <div className="flex flex-wrap gap-2 text-[11px] items-center">
          <label className="flex items-center gap-1">
            <span className="text-muted">category</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value as any)}
              className="h-7 px-2 rounded bg-bg-deep border border-line text-white"
            >
              {CATEGORIES.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <span className="text-muted">level</span>
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value as any)}
              className="h-7 px-2 rounded bg-bg-deep border border-line text-white"
            >
              {LEVELS.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="flex items-center gap-1">
            <span className="text-muted">search</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="scope or text"
              className="h-7 px-2 rounded bg-bg-deep border border-line text-white w-56"
            />
          </label>
          <label className="flex items-center gap-1 text-white">
            <input type="checkbox" checked={onlySuspicious} onChange={(e) => setOnlySuspicious(e.target.checked)} />
            only suspicious
          </label>
          <label className="flex items-center gap-1 text-white">
            <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
            follow new entries
          </label>
          <span className="ml-auto text-muted">{filtered.length} matching</span>
        </div>
      </PanelCard>

      {/* Stream */}
      <div className="grid grid-cols-12 gap-3">
        <PanelCard title="Stream" className="col-span-7">
          <div
            ref={(el) => {
              if (follow && el) el.scrollTop = el.scrollHeight;
            }}
            className="max-h-[60vh] overflow-auto font-mono text-[11px]"
          >
            {filtered.length === 0 && (
              <div className="text-muted p-4 text-center">no entries</div>
            )}
            {filtered.map((e) => (
              <button
                key={e.id}
                onClick={() => setSelected(e)}
                className={`w-full text-left px-2 py-1 border-b border-line/30 hover:bg-line/40 flex gap-2 ${
                  selected?.id === e.id ? "bg-line/60" : ""
                } ${e.suspicious ? "bg-danger/10" : ""}`}
              >
                <span className="text-muted">{new Date(e.ts).toISOString().slice(11, 23)}</span>
                <span
                  className="px-1 rounded text-[9px] uppercase tracking-wider"
                  style={{ color: LEVEL_COLOR[e.level] }}
                >
                  {e.level}
                </span>
                <span className="text-accent">{e.category}</span>
                <span className="text-info truncate max-w-[180px]">{e.scope}</span>
                <span className="text-white flex-1 truncate">{e.message}</span>
                {e.durationMs !== undefined && (
                  <span className="text-muted">{e.durationMs}ms</span>
                )}
                {e.suspicious && <span className="text-danger">⚠{e.violations?.length}</span>}
              </button>
            ))}
          </div>
        </PanelCard>

        <PanelCard title="Entry details" className="col-span-5">
          {!selected ? (
            <div className="text-[11px] text-muted">Click a log entry to inspect its payload.</div>
          ) : (
            <div className="space-y-3 text-[11px]">
              <div className="grid grid-cols-2 gap-2">
                <KV k="id"        v={`#${selected.id}`} />
                <KV k="time"      v={new Date(selected.ts).toISOString().slice(11, 23)} />
                <KV k="category"  v={selected.category} />
                <KV k="level"     v={<span style={{ color: LEVEL_COLOR[selected.level] }}>{selected.level}</span>} />
                <KV k="scope"     v={selected.scope} />
                <KV k="duration"  v={selected.durationMs !== undefined ? `${selected.durationMs}ms` : "—"} />
              </div>
              <div>
                <div className="text-muted uppercase tracking-widest text-[10px] mb-1">message</div>
                <div className="text-white">{selected.message}</div>
              </div>
              {selected.violations && selected.violations.length > 0 && (
                <div>
                  <div className="text-danger uppercase tracking-widest text-[10px] mb-1">
                    violations ({selected.violations.length})
                  </div>
                  <ul className="space-y-1">
                    {selected.violations.map((v, i) => (
                      <li
                        key={i}
                        className={`p-1.5 rounded border ${
                          v.severity === "danger"
                            ? "border-danger/60 bg-danger/10 text-danger"
                            : v.severity === "warn"
                            ? "border-warn/60 bg-warn/10 text-warn"
                            : "border-info/60 bg-info/10 text-info"
                        }`}
                      >
                        <div className="font-mono">{v.field}</div>
                        <div>expected: {v.expected}</div>
                        <div>actual: {JSON.stringify(v.actual)}</div>
                        {v.note && <div className="italic opacity-80">{v.note}</div>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {selected.data !== undefined && (
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-muted uppercase tracking-widest text-[10px]">payload</span>
                    <button
                      onClick={() =>
                        navigator.clipboard.writeText(JSON.stringify(selected.data, null, 2))
                      }
                      className="px-2 h-5 rounded bg-line text-[10px] text-white"
                    >
                      copy JSON
                    </button>
                  </div>
                  <pre className="bg-black/60 border border-line rounded p-2 text-muted max-h-72 overflow-auto whitespace-pre-wrap break-all">
                    {safeStringify(selected.data)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </PanelCard>
      </div>
    </Page>
  );
}

function safeStringify(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function Stat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-bg-panel border border-line rounded p-2">
      <div className="text-xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-line/40 py-0.5">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-white truncate max-w-[60%] text-right">{v}</span>
    </div>
  );
}
