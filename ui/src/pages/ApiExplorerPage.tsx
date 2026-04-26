import { useEffect, useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type ApiEndpoint } from "../api";

export default function ApiExplorerPage() {
  const [catalog, setCatalog] = useState<ApiEndpoint[]>([]);
  const [selected, setSelected] = useState<ApiEndpoint | null>(null);
  const [group, setGroup] = useState<string>("all");

  useEffect(() => {
    api.getApiCatalog().then((r) => {
      setCatalog(r);
      setSelected(r[0] ?? null);
    });
  }, []);

  const groups = useMemo(() => {
    const g = new Map<string, number>();
    catalog.forEach((e) => g.set(e.group, (g.get(e.group) ?? 0) + 1));
    return Array.from(g.entries());
  }, [catalog]);

  const visible = group === "all" ? catalog : catalog.filter((e) => e.group === group);

  const methodColor = (m: ApiEndpoint["method"]) =>
    m === "GET" ? "#22c55e" : m === "POST" ? "#38bdf8" : m === "PUT" ? "#a855f7" : "#ef4444";

  return (
    <Page
      title="API explorer (debug)"
      subtitle={`${catalog.length} endpoint(s) across ${groups.length} group(s) — mock samples`}
    >
      <div className="grid grid-cols-12 gap-3 h-[calc(100%-0px)]">
        <div className="col-span-4 flex flex-col gap-2">
          <PanelCard title="Groups">
            <div className="flex flex-wrap gap-1">
              <button
                onClick={() => setGroup("all")}
                className={`text-[11px] px-2 h-6 rounded ${
                  group === "all" ? "bg-line text-white" : "bg-bg-deep text-muted hover:text-white"
                }`}
              >
                all ({catalog.length})
              </button>
              {groups.map(([g, n]) => (
                <button
                  key={g}
                  onClick={() => setGroup(g)}
                  className={`text-[11px] px-2 h-6 rounded ${
                    group === g ? "bg-line text-white" : "bg-bg-deep text-muted hover:text-white"
                  }`}
                >
                  {g} ({n})
                </button>
              ))}
            </div>
          </PanelCard>
          <PanelCard title="Endpoints">
            <div className="flex flex-col gap-1 max-h-[60vh] overflow-auto">
              {visible.map((e) => (
                <button
                  key={e.method + e.path}
                  onClick={() => setSelected(e)}
                  className={`text-left px-2 py-1.5 rounded border flex items-center gap-2 ${
                    selected === e ? "border-info bg-line/40" : "border-line/50 hover:border-info/50"
                  }`}
                >
                  <span
                    className="text-[9px] font-mono w-10 text-center rounded"
                    style={{ background: methodColor(e.method) + "30", color: methodColor(e.method) }}
                  >
                    {e.method}
                  </span>
                  <span className="text-[11px] font-mono text-white truncate flex-1">{e.path}</span>
                </button>
              ))}
            </div>
          </PanelCard>
        </div>
        <div className="col-span-8 flex flex-col gap-2">
          {selected ? (
            <>
              <PanelCard>
                <div className="flex items-center gap-2">
                  <span
                    className="text-[10px] font-mono w-12 text-center rounded px-1 py-0.5"
                    style={{
                      background: methodColor(selected.method) + "30",
                      color: methodColor(selected.method),
                    }}
                  >
                    {selected.method}
                  </span>
                  <span className="text-sm font-mono text-white">{selected.path}</span>
                  <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-line text-muted">
                    {selected.group}
                  </span>
                </div>
                <div className="text-[12px] text-muted mt-2">{selected.description}</div>
              </PanelCard>
              <PanelCard title="Sample response" className="flex-1 min-h-0 flex flex-col">
                <pre className="text-[11px] bg-black/60 border border-line rounded p-2 overflow-auto max-h-[60vh] text-muted font-mono whitespace-pre-wrap">
                  {JSON.stringify(selected.sampleResponse, null, 2)}
                </pre>
              </PanelCard>
            </>
          ) : (
            <div className="text-[11px] text-muted">Select an endpoint.</div>
          )}
        </div>
      </div>
    </Page>
  );
}
