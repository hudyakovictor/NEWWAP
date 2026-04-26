/**
 * Boot-time self-test: runs every backend endpoint once with a sensible
 * default argument set and logs a consolidated summary. Useful to spot
 * regressions immediately after a code change — you open the app, open
 * DevTools, and see a one-shot validation report.
 */

import { api } from "../api";
import { log, getAllLogs } from "./logger";
import { PHOTOS } from "../mock/photos";

export async function runSelfTest() {
  log.info("self_test", "self_test:start", "Starting boot self-test across all endpoints");
  const t0 = performance.now();

  const a = PHOTOS[30]?.id;
  const b = PHOTOS[PHOTOS.length - 40]?.id;

  const checks: Array<{ name: string; run: () => Promise<unknown> }> = [
    { name: "getTimeline",        run: () => api.getTimeline() },
    { name: "listPhotos",         run: () => api.listPhotos({ limit: 50 }) },
    { name: "getPhotoDetail",     run: () => api.getPhotoDetail(a) },
    { name: "similarPhotos",      run: () => api.similarPhotos(a, 8) },
    { name: "getCalibration",     run: () => api.getCalibration() },
    { name: "photosInBucket",     run: () => api.photosInBucket("frontal", "daylight") },
    { name: "listJobs",           run: () => api.listJobs() },
    { name: "listInvestigations", run: () => api.listInvestigations() },
    { name: "listAnomalies",      run: () => api.listAnomalies() },
    { name: "getPipelineStages",  run: () => api.getPipelineStages() },
    { name: "getCacheSummary",    run: () => api.getCacheSummary() },
    { name: "getAgeingSeries",    run: () => api.getAgeingSeries() },
    { name: "getEvidence",        run: () => api.getEvidence(a, b) },
    { name: "getApiCatalog",      run: () => api.getApiCatalog() },
    { name: "comparisonMatrix",   run: () => api.comparisonMatrix([a, b, PHOTOS[100]?.id]) },
  ];

  const results: Array<{ name: string; status: "ok" | "fail"; violations: number; ms: number }> = [];
  for (const c of checks) {
    const ts = performance.now();
    try {
      await c.run();
      const before = getAllLogs().length;
      // Find last log for this api name to count its violations
      const last = getAllLogs()
        .slice()
        .reverse()
        .find((e) => e.scope === `api:${c.name}` && e.durationMs !== undefined);
      const violations = last?.violations?.length ?? 0;
      results.push({
        name: c.name,
        status: "ok",
        violations,
        ms: +(performance.now() - ts).toFixed(1),
      });
      void before;
    } catch (e) {
      log.error("self_test", `self_test:${c.name}`, `${c.name} threw during self-test`, e);
      results.push({
        name: c.name,
        status: "fail",
        violations: 0,
        ms: +(performance.now() - ts).toFixed(1),
      });
    }
  }

  const totalMs = +(performance.now() - t0).toFixed(1);
  const failed = results.filter((r) => r.status === "fail").length;
  const suspicious = results.filter((r) => r.violations > 0).length;

  log.info(
    "self_test",
    "self_test:summary",
    `Self-test complete in ${totalMs}ms — ${results.length} endpoints, ${failed} failed, ${suspicious} with validation violations`,
    results
  );

  // Pretty console.table for quick review
  // eslint-disable-next-line no-console
  console.groupCollapsed(
    `%cdeeputin self-test%c ${results.length} endpoints, ${failed} failed, ${suspicious} suspicious, ${totalMs}ms`,
    "background:#166534;color:#bbf7d0;padding:1px 4px;border-radius:2px;font-weight:bold",
    "color:#cfd8e6"
  );
  // eslint-disable-next-line no-console
  console.table(results);
  // eslint-disable-next-line no-console
  console.groupEnd();

  // Expose on window for on-demand rerun
  (window as any).deeputin.selfTest = runSelfTest;
  (window as any).deeputin.lastSelfTest = { at: new Date().toISOString(), results, totalMs, failed, suspicious };

  return { results, totalMs, failed, suspicious };
}
