/**
 * Headless audit runner — the entrypoint the AI assistant uses to inspect
 * the project state from the command line without a browser.
 *
 * Usage:   npm run audit
 * Writes:  ./audit-report.json   (full machine-readable report)
 * Prints:  compact AI-friendly summary to stdout
 */

import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

// Stub window.deeputin away — logger references window at import time
(globalThis as any).window = (globalThis as any).window ?? {};

import { loggedBackend } from "../src/api/logged";
import { runAudit } from "../src/debug/audit";

async function runOnce(quiet = false) {
  const report = await runAudit(loggedBackend);
  const path = resolve(process.cwd(), "audit-report.json");
  writeFileSync(path, JSON.stringify(report, null, 2));
  if (quiet) {
    const ok = report.endpoints.filter((e) => e.status === "ok").length;
    console.log(
      `[${new Date().toISOString()}] audit: total=${report.counts.total} ` +
        `d=${report.counts.danger} w=${report.counts.warn} i=${report.counts.info} ` +
        `endpoints=${ok}/${report.endpoints.length} (${report.durationMs}ms)`
    );
  }
  return report;
}

async function main() {
  const args = process.argv.slice(2);
  const watch = args.includes("--watch");
  const intervalIdx = args.indexOf("--interval");
  const intervalMs = intervalIdx >= 0 ? +args[intervalIdx + 1] || 30_000 : 30_000;

  if (watch) {
    console.log(`Watch mode — re-running audit every ${intervalMs}ms. Ctrl+C to stop.`);
    let prevTotal = -1;
    let prevDanger = -1;
    /* eslint-disable no-constant-condition */
    while (true) {
      const r = await runOnce(true);
      if (r.counts.total !== prevTotal || r.counts.danger !== prevDanger) {
        if (prevTotal >= 0) {
          console.log(
            `  ↳ change: total ${prevTotal}→${r.counts.total}, danger ${prevDanger}→${r.counts.danger}`
          );
        }
        prevTotal = r.counts.total;
        prevDanger = r.counts.danger;
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
  }

  const report = await runAudit(loggedBackend);

  const path = resolve(process.cwd(), "audit-report.json");
  writeFileSync(path, JSON.stringify(report, null, 2));

  // Plain-text AI-friendly summary
  const divider = "─".repeat(72);
  console.log(divider);
  console.log(`DEEPUTIN audit  ·  ${report.generatedAt}  ·  ${report.durationMs}ms`);
  console.log(divider);
  console.log(report.summary);
  console.log();

  // Endpoint table
  console.log("Endpoints:");
  for (const e of report.endpoints) {
    const icon = e.status === "ok" ? "✓" : "✗";
    console.log(`  ${icon} ${e.name.padEnd(22)} ${String(e.ms).padStart(5)}ms${e.note ? "  " + e.note : ""}`);
  }
  console.log();

  // Findings grouped
  if (report.findings.length === 0) {
    console.log("No findings. System is green.");
  } else {
    const bySev: Record<string, typeof report.findings> = { danger: [], warn: [], info: [] };
    for (const f of report.findings) bySev[f.severity].push(f);
    for (const sev of ["danger", "warn", "info"] as const) {
      if (bySev[sev].length === 0) continue;
      console.log(`${sev.toUpperCase()} (${bySev[sev].length}):`);
      for (const f of bySev[sev]) {
        console.log(`  [${f.area}] ${f.id}`);
        console.log(`    ${f.message}`);
        if (f.expected !== undefined) console.log(`    expected: ${f.expected}`);
        if (f.actual !== undefined) console.log(`    actual:   ${JSON.stringify(f.actual)}`);
        if (f.hint) console.log(`    hint:     ${f.hint}`);
      }
      console.log();
    }
  }

  console.log("TZ coverage:");
  for (const t of report.tzCoverage) {
    console.log(`  • ${t.topic}`);
    console.log(`      ↳ ${t.impl}`);
  }

  console.log();
  console.log(divider);
  console.log(`Report written to ${path}`);
  console.log(divider);

  // Non-zero exit on danger so CI/scripts can notice
  if (report.counts.danger > 0) process.exit(2);
}

main().catch((e) => {
  console.error("audit failed:", e);
  process.exit(1);
});
