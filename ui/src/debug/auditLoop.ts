/**
 * Auto-audit loop — runs the full invariant suite every N seconds and
 * exposes the latest report via a tiny pub/sub. The TopBar subscribes
 * to render a live badge with the current finding count.
 *
 * The loop also pushes a delta-aware log entry whenever the finding
 * count changes, so the AI can spot regressions just by scanning logs.
 */

import { runAudit, type AuditReport } from "./audit";
import { api } from "../api";
import { log } from "./logger";
import { recordAudit } from "./auditHistory";

let latest: AuditReport | null = null;
const subs = new Set<(r: AuditReport) => void>();
let timerId: number | null = null;

export function getLatestAudit(): AuditReport | null {
  return latest;
}

export function subscribeAudit(fn: (r: AuditReport) => void): () => void {
  subs.add(fn);
  if (latest) fn(latest);
  return () => {
    subs.delete(fn);
  };
}

async function tick() {
  try {
    const prev = latest;
    const r = await runAudit(api);
    latest = r;
    (window as any).deeputin.lastAudit = r;
    recordAudit(r);
    if (
      !prev ||
      prev.counts.total !== r.counts.total ||
      prev.counts.danger !== r.counts.danger ||
      prev.counts.warn !== r.counts.warn
    ) {
      log.info(
        "self_test",
        "audit:delta",
        `Audit ${prev ? "changed" : "initial"}: ${r.counts.total} findings (danger=${r.counts.danger}, warn=${r.counts.warn}, info=${r.counts.info})`,
        {
          previous: prev?.counts,
          current: r.counts,
          summary: r.summary,
        }
      );
      if (r.counts.danger > 0) {
        log.error(
          "validation",
          "audit:danger",
          `Audit RED — ${r.counts.danger} danger-level finding(s)`,
          r.findings.filter((f) => f.severity === "danger")
        );
      }
    }
    subs.forEach((fn) => fn(r));
  } catch (e) {
    log.error("self_test", "audit:tick_failed", "Auto-audit tick threw", e);
  }
}

export function startAuditLoop(intervalMs = 60000) {
  if (timerId !== null) return;
  // Run once immediately, then on a timer.
  void tick();
  timerId = window.setInterval(() => void tick(), intervalMs);
  log.info("self_test", "audit:loop_started", `Auto-audit loop started (every ${intervalMs}ms)`, { intervalMs });
}

export function stopAuditLoop() {
  if (timerId === null) return;
  window.clearInterval(timerId);
  timerId = null;
  log.info("self_test", "audit:loop_stopped", "Auto-audit loop stopped");
}

if (typeof window !== "undefined") {
  (window as any).deeputin = (window as any).deeputin ?? {};
  (window as any).deeputin.audit = () => tick().then(() => latest);
  (window as any).deeputin.startAuditLoop = startAuditLoop;
  (window as any).deeputin.stopAuditLoop = stopAuditLoop;
}
