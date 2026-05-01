/**
 * Audit runner — the autonomous entrypoint that the AI assistant uses to
 * assess notebook health without the user having to tell it anything.
 *
 * Runs in both:
 *   - the browser (AuditPage + boot auto-audit), and
 *   - Node (scripts/audit.ts → `npm run audit`) where it writes a JSON file.
 *
 * Produces a single AuditReport with:
 *   - findings[]    — every invariant violation, grouped & severity-scored
 *   - timings       — per-invariant wall-clock
 *   - environment   — node/browser, timestamp, git-ish metadata if available
 *   - tzCoverage    — declared TZ topics + implementation pointers
 *   - endpoints     — ok/fail table from the backend self-test
 *   - summary       — short human+AI readable verdict
 */

import type { Backend } from "../api/types";
import { ALL_INVARIANTS, tzCoverageMap, type Finding, type Severity } from "./invariants";
import { DEEP_INVARIANTS } from "./invariants_deep";
import { checkTzAutoCoverage } from "./tzCoverage";
import { PHOTOS } from "../mock/photos";

export interface EndpointResult {
  name: string;
  status: "ok" | "fail";
  ms: number;
  note?: string;
}

export interface AuditReport {
  generatedAt: string;
  durationMs: number;
  environment: {
    runtime: "browser" | "node";
    userAgent?: string;
    nodeVersion?: string;
  };
  endpoints: EndpointResult[];
  findings: Finding[];
  timings: Record<string, number>;
  counts: Record<Severity, number> & { total: number; byArea: Record<string, number> };
  tzCoverage: Array<{ topic: string; impl: string }>;
  summary: string;
}

export async function runAudit(api: Backend): Promise<AuditReport> {
  const t0 = Date.now();
  const isBrowser = typeof window !== "undefined" && typeof document !== "undefined";

  const findings: Finding[] = [];
  const timings: Record<string, number> = {};

  for (const inv of [...ALL_INVARIANTS, ...DEEP_INVARIANTS]) {
    const s = Date.now();
    try {
      const out = await inv.run({ api });
      findings.push(...out);
    } catch (err) {
      findings.push({
        id: `audit.invariant_threw.${inv.id}`,
        area: "api",
        severity: "danger",
        message: `Invariant '${inv.id}' threw`,
        actual: String(err instanceof Error ? err.message : err),
        hint: "Check the invariant implementation in src/debug/invariants*.ts",
      });
    }
    timings[inv.id] = Date.now() - s;
  }

  // TZ auto-coverage (parses about platform.txt and looks for unmapped topics)
  {
    const s = Date.now();
    try {
      const out = await checkTzAutoCoverage();
      findings.push(...out);
    } catch (err) {
      findings.push({
        id: "audit.tz_auto_coverage_threw",
        area: "tz",
        severity: "info",
        message: "TZ auto-coverage check threw (non-fatal)",
        actual: String(err instanceof Error ? err.message : err),
      });
    }
    timings["tz_auto_coverage"] = Date.now() - s;
  }

  // Asset existence check is Node-only; in the browser it short-circuits to [].
  if (!isBrowser) {
    const s = Date.now();
    try {
      const m = await import("./assets_node");
      const out = await m.checkAssetsExist();
      findings.push(...out);
    } catch (err) {
      findings.push({
        id: "audit.assets_check_threw",
        area: "consistency",
        severity: "info",
        message: "Asset existence check threw (non-fatal)",
        actual: String(err instanceof Error ? err.message : err),
      });
    }
    timings["assets_node"] = Date.now() - s;
  }

  // Endpoint self-test (in addition to invariants)
  const endpoints = await runEndpointSelfTest(api);

  // Counts
  const counts = {
    info: 0, warn: 0, danger: 0, total: findings.length,
    byArea: {} as Record<string, number>,
  };
  for (const f of findings) {
    counts[f.severity]++;
    counts.byArea[f.area] = (counts.byArea[f.area] ?? 0) + 1;
  }

  const summary = buildSummary(endpoints, findings, counts);

  return {
    generatedAt: new Date().toISOString(),
    durationMs: Date.now() - t0,
    environment: {
      runtime: isBrowser ? "browser" : "node",
      userAgent: isBrowser ? navigator.userAgent : undefined,
      nodeVersion: !isBrowser ? (globalThis as any).process?.version : undefined,
    },
    endpoints,
    findings,
    timings,
    counts,
    tzCoverage: tzCoverageMap(),
    summary,
  };
}

async function runEndpointSelfTest(api: Backend): Promise<EndpointResult[]> {
  // Get real photo IDs from backend instead of using mock IDs
  let testIds: string[] = [];
  try {
    const list = await api.listPhotos({ limit: 50 });
    testIds = list.items.map((p: any) => p.photo_id || p.id).filter(Boolean);
  } catch {
    // Fallback to mock if backend is unavailable
    testIds = [PHOTOS[30]?.id, PHOTOS[PHOTOS.length - 40]?.id, PHOTOS[100]?.id].filter(Boolean) as string[];
  }
  const a = testIds[0] || PHOTOS[0]?.id || "";
  const b = testIds[Math.min(10, testIds.length - 1)] || a;
  const c = testIds[Math.min(20, testIds.length - 1)] || a;
  const cases: Array<{ name: string; run: () => Promise<unknown> }> = [
    { name: "getTimeline",         run: () => api.getTimeline() },
    { name: "listPhotos",          run: () => api.listPhotos({ limit: 20 }) },
    { name: "getPhotoDetail",      run: () => api.getPhotoDetail(a) },
    { name: "similarPhotos",       run: () => api.similarPhotos(a, 8) },
    { name: "getCalibration",      run: () => api.getCalibration() },
    { name: "photosInBucket",      run: () => api.photosInBucket("frontal", "daylight") },
    { name: "listJobs",            run: () => api.listJobs() },
    { name: "listInvestigations",  run: () => api.listInvestigations() },
    { name: "listAnomalies",       run: () => api.listAnomalies() },
    { name: "getPipelineStages",   run: () => api.getPipelineStages() },
    { name: "getCacheSummary",     run: () => api.getCacheSummary() },
    { name: "getAgeingSeries",     run: () => api.getAgeingSeries() },
    { name: "getEvidence",         run: () => api.getEvidence(a, b) },
    { name: "getApiCatalog",       run: () => api.getApiCatalog() },
    { name: "comparisonMatrix",    run: () => api.comparisonMatrix([a, b, c]) },
  ];
  const out: EndpointResult[] = [];
  for (const c of cases) {
    const s = Date.now();
    try {
      await c.run();
      out.push({ name: c.name, status: "ok", ms: Date.now() - s });
    } catch (err) {
      out.push({
        name: c.name,
        status: "fail",
        ms: Date.now() - s,
        note: String(err instanceof Error ? err.message : err),
      });
    }
  }
  return out;
}

function buildSummary(
  endpoints: EndpointResult[],
  _findings: Finding[],
  counts: AuditReport["counts"]
): string {
  const failedEndpoints = endpoints.filter((e) => e.status === "fail");
  const lines: string[] = [];
  if (failedEndpoints.length === 0 && counts.danger === 0 && counts.warn === 0) {
    lines.push("✓ AUDIT GREEN — all invariants pass, all endpoints respond, no validation warnings.");
  } else if (counts.danger > 0) {
    lines.push(`✗ AUDIT RED — ${counts.danger} danger-level finding(s). Fix before publishing.`);
  } else if (counts.warn > 0) {
    lines.push(`⚠ AUDIT YELLOW — ${counts.warn} warning(s), no dangers.`);
  } else {
    lines.push(`ℹ AUDIT GREEN w/ notes — ${counts.info} info-level finding(s).`);
  }
  lines.push(`Endpoints: ${endpoints.length - failedEndpoints.length}/${endpoints.length} ok` +
             (failedEndpoints.length ? ` · failures: ${failedEndpoints.map((e) => e.name).join(", ")}` : ""));
  lines.push(`Findings total: ${counts.total} (danger=${counts.danger}, warn=${counts.warn}, info=${counts.info}).`);
  const areas = Object.entries(counts.byArea).sort((a, b) => b[1] - a[1]);
  if (areas.length) lines.push(`By area: ${areas.map(([a, n]) => `${a}=${n}`).join(" · ")}.`);
  return lines.join("\n");
}
