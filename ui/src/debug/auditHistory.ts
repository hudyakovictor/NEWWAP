/**
 * Lightweight audit history kept in localStorage. We never store full
 * findings (could be large) — just summarized counts so that the AuditPage
 * can show a trend and the AI can see whether things got better or worse.
 *
 * On every audit tick:
 *   - append a snapshot
 *   - compare against the previous snapshot
 *   - emit a regression log entry if findings increased
 *
 * The buffer is capped at 50 entries.
 */

import type { AuditReport } from "./audit";
import { log } from "./logger";

const STORAGE_KEY = "deeputin.audit.history";
const MAX_ENTRIES = 50;

export interface AuditSnapshot {
  at: string;
  durationMs: number;
  total: number;
  danger: number;
  warn: number;
  info: number;
  endpointsOk: number;
  endpointsTotal: number;
  byArea: Record<string, number>;
  summary: string;
}

function load(): AuditSnapshot[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const v = JSON.parse(raw);
    return Array.isArray(v) ? v : [];
  } catch {
    return [];
  }
}

function save(list: AuditSnapshot[]) {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(-MAX_ENTRIES)));
  } catch {
    /* ignore storage errors */
  }
}

export function recordAudit(report: AuditReport): { current: AuditSnapshot; prev?: AuditSnapshot } {
  const list = load();
  const snap: AuditSnapshot = {
    at: report.generatedAt,
    durationMs: report.durationMs,
    total: report.counts.total,
    danger: report.counts.danger,
    warn: report.counts.warn,
    info: report.counts.info,
    endpointsOk: report.endpoints.filter((e) => e.status === "ok").length,
    endpointsTotal: report.endpoints.length,
    byArea: report.counts.byArea,
    summary: report.summary,
  };
  const prev = list[list.length - 1];
  list.push(snap);
  save(list);

  if (prev) {
    if (snap.danger > prev.danger || snap.warn > prev.warn) {
      log.error(
        "validation",
        "audit:regression",
        `Audit regression: danger ${prev.danger}→${snap.danger}, warn ${prev.warn}→${snap.warn}`,
        { prev, snap }
      );
    } else if (snap.total < prev.total) {
      log.info(
        "self_test",
        "audit:improvement",
        `Audit improved: total ${prev.total}→${snap.total}`,
        { prev, snap }
      );
    }
  }
  return { current: snap, prev };
}

export function getHistory(): AuditSnapshot[] {
  return load();
}

export function clearHistory() {
  if (typeof localStorage === "undefined") return;
  localStorage.removeItem(STORAGE_KEY);
}

if (typeof window !== "undefined") {
  (window as any).deeputin = (window as any).deeputin ?? {};
  (window as any).deeputin.history = getHistory;
  (window as any).deeputin.clearHistory = clearHistory;
}
