export type PageId =
  | "timeline"
  | "photos"
  | "pairs"
  | "matrix"
  | "evidence"
  | "ageing"
  | "anomalies"
  | "investigations"
  | "calibration"
  | "pipeline"
  | "cache"
  | "jobs"
  | "reports"
  | "report_builder"
  | "api"
  | "logs"
  | "ground_truth"
  | "audit"
  | "signals"
  | "progress"
  | "clusters"
  | "iterations"
  | "diary"
  | "settings";

const MENU_GROUPS: { title: string; items: { id: PageId; label: string }[] }[] = [
  {
    title: "Main",
    items: [
      { id: "progress", label: "Progress" },
      { id: "iterations", label: "Iterations" },
      { id: "timeline", label: "Timeline" },
      { id: "photos", label: "Photos" },
      { id: "pairs", label: "Pair" },
      { id: "anomalies", label: "Anomalies" },
      { id: "investigations", label: "Cases" },
    ],
  },
  {
    title: "Debug",
    items: [
      { id: "audit", label: "Audit" },
      { id: "logs", label: "Logs" },
      { id: "diary", label: "Дневник" },
      { id: "ground_truth", label: "Ground truth" },
      { id: "signals", label: "Real signals" },
      { id: "clusters", label: "Visual clusters" },
      { id: "matrix", label: "N×N" },
      { id: "evidence", label: "Evidence" },
      { id: "ageing", label: "Ageing" },
      { id: "pipeline", label: "Pipeline" },
      { id: "cache", label: "Cache" },
      { id: "api", label: "API" },
    ],
  },
  {
    title: "Ops",
    items: [
      { id: "calibration", label: "Calibration" },
      { id: "jobs", label: "Jobs" },
      { id: "reports", label: "Reports" },
      { id: "report_builder", label: "Report+" },
      { id: "settings", label: "Settings" },
    ],
  },
];

import { useEffect, useState } from "react";
import { subscribeAudit } from "../debug/auditLoop";
import type { AuditReport } from "../debug/audit";

export default function TopBar({
  current,
  onNav,
}: {
  current: PageId;
  onNav: (p: PageId) => void;
}) {
  const [audit, setAudit] = useState<AuditReport | null>(null);
  useEffect(() => subscribeAudit(setAudit), []);
  return (
    <header className="flex items-center h-11 px-3 bg-bg-deep border-b border-line select-none shrink-0">
      <button
        onClick={() => onNav("timeline")}
        className="flex items-center gap-2 pr-4 border-r border-line mr-4"
      >
        <div className="w-6 h-6 rounded-md bg-gradient-to-br from-accent to-info grid place-items-center text-[10px] font-bold text-white">
          DP
        </div>
        <div className="flex flex-col leading-tight text-left">
          <span className="text-xs font-semibold text-white tracking-wide">DEEPUTIN</span>
          <span className="text-[10px] text-muted -mt-0.5">investigation · 1999–2025</span>
        </div>
      </button>

      <nav className="flex items-center gap-3 overflow-auto">
        {MENU_GROUPS.map((g) => (
          <div key={g.title} className="flex items-center gap-1">
            <span className="text-[9px] uppercase tracking-wider text-muted px-1 border-r border-line/60 pr-2 mr-1">
              {g.title}
            </span>
            {g.items.map((m) => (
              <button
                key={m.id}
                onClick={() => onNav(m.id)}
                className={`px-2 h-7 rounded-md text-[11px] whitespace-nowrap transition-colors ${
                  current === m.id
                    ? "bg-line text-white"
                    : "text-muted hover:text-white hover:bg-line/60"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2 text-[11px] text-muted shrink-0">
        <span className="px-2 py-1 rounded bg-line/60 text-[10px]">
          <span className="text-ok">●</span> mock
        </span>
        <button
          onClick={() => onNav("audit")}
          className="px-2 py-1 rounded text-[10px] border border-line/60 hover:bg-line/40"
          title="Click for full audit report"
        >
          {audit ? (
            audit.counts.danger > 0 ? (
              <span className="text-danger font-semibold">⚠ {audit.counts.danger}d / {audit.counts.warn}w</span>
            ) : audit.counts.warn > 0 ? (
              <span className="text-warn">⚠ {audit.counts.warn}w / {audit.counts.info}i</span>
            ) : audit.counts.total > 0 ? (
              <span className="text-info">ℹ {audit.counts.info}</span>
            ) : (
              <span className="text-ok">✓ green</span>
            )
          ) : (
            <span className="text-muted">audit…</span>
          )}
        </button>
        <span className="px-2 py-1 rounded border border-line text-muted text-[10px]">⌘K</span>
      </div>
    </header>
  );
}
