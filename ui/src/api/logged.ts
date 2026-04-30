/**
 * Logging + validation middleware wrapped around the raw mock backend.
 * Every method call is timed, every response is run through its validator
 * and any resulting violations are attached to the log entry.
 *
 * Keeping this as a thin wrapper means the actual backend (mock or future
 * HTTP) stays clean and deterministic.
 */

import { mockBackend } from "./mock";
import type { Backend, EvidenceBreakdown } from "./types";
import { log } from "../debug/logger";
import {
  validateTimeline,
  validatePhotoList,
  validatePhotoDetail,
  validateEvidence,
  validateCalibration,
  validateJobs,
  validateAnomalies,
  validatePipeline,
  validateCache,
  validateAgeing,
} from "../debug/validators";

const API_BASE = "http://localhost:8000";

async function fetchJson(path: string, options: RequestInit = {}) {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    signal: AbortSignal.timeout(10000), // 10s global timeout
  });
  if (!resp.ok) throw new Error(`Backend error: ${resp.statusText}`);
  return resp.json();
}

async function fetchEvidence(aId: string, bId: string): Promise<EvidenceBreakdown> {
  try {
    return await fetchJson(`/api/evidence/compare?photo_id_a=${encodeURIComponent(aId)}&photo_id_b=${encodeURIComponent(bId)}`, {
      method: "POST",
    });
  } catch (err) {
    console.warn(`[getEvidence] Falling back to mock: ${err instanceof Error ? err.message : String(err)}`);
    return mockBackend.getEvidence(aId, bId);
  }
}

async function fetchComparisonMatrix(ids: string[]): Promise<number[][]> {
  try {
    return await fetchJson(`/api/evidence/matrix`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ids),
    });
  } catch (err) {
    console.warn(`[comparisonMatrix] Falling back to mock: ${err}`);
    return mockBackend.comparisonMatrix(ids);
  }
}

function wrap<T extends (...args: any[]) => Promise<any>>(
  name: string,
  fn: T,
  validator?: (result: Awaited<ReturnType<T>>, args: Parameters<T>) => import("../debug/logger").Violation[],
): T {
  return (async (...args: Parameters<T>) => {
    const t0 = performance.now();
    try {
      const result = await fn(...args);
      const durationMs = +(performance.now() - t0).toFixed(1);
      const violations = validator ? validator(result, args) : [];
      if (violations.length) {
        log.validation(`api:${name}`, `${name} validated with ${violations.length} violation(s)`, { args, result, durationMs }, violations);
      } else {
        log.debug("api", `api:${name}`, `${name} ok`, { args, result, durationMs });
      }
      log.trace("api", `api:${name}:timing`, `${durationMs}ms`, { durationMs, args });
      return result;
    } catch (err) {
      const durationMs = +(performance.now() - t0).toFixed(1);
      log.error("api", `api:${name}`, `${name} threw`, { args, err, durationMs });
      throw err;
    }
  }) as T;
}

export const loggedBackend: Backend = {
  getTimeline: wrap("getTimeline", () => fetchJson("/api/timeline-summary"), (r) => validateTimeline(r)),
  listPhotos:  wrap("listPhotos", (_q) => fetchJson(`/api/photos/main`), (r) => validatePhotoList(r)),
  getPhotoDetail: wrap("getPhotoDetail", (id) => fetchJson(`/api/photo/main/${id}`), (r) => validatePhotoDetail(r)),
  similarPhotos: wrap("similarPhotos", (id) => fetchJson(`/api/similar-photos/${id}`)),
  getCalibration: wrap("getCalibration", () => fetchJson("/api/calibration/summary"), (r) => validateCalibration(r)),
  photosInBucket: wrap("photosInBucket", (p, l) => mockBackend.photosInBucket(p, l)), // Keep mock for now or implement in main.py
  listJobs:       wrap("listJobs", () => fetchJson("/api/jobs"), (r) => validateJobs(r)),
  startJob:       wrap("startJob", (kind) => fetchJson(`/api/jobs/${kind === "extract" ? "extract" : "recompute-metrics"}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ dataset: "main", limit: 100 }),
  })),
  listInvestigations: wrap("listInvestigations", mockBackend.listInvestigations),
  upsertInvestigation: wrap("upsertInvestigation", mockBackend.upsertInvestigation),
  deleteInvestigation: wrap("deleteInvestigation", mockBackend.deleteInvestigation),
  listAnomalies:  wrap("listAnomalies", () => fetchJson("/api/anomalies"), (r) => validateAnomalies(r)),
  uploadPhotos:   wrap("uploadPhotos", async (files) => {
    const formData = new FormData();
    files.forEach(f => formData.append("file", f));
    return fetchJson("/api/upload", { method: "POST", body: formData });
  }),

  getPipelineStages: wrap("getPipelineStages", () => fetchJson("/api/pipeline/stages"), (r) => validatePipeline(r)),
  getCacheSummary:   wrap("getCacheSummary", () => fetchJson("/api/cache/summary"), (r) => validateCache(r)),
  getAgeingSeries:   wrap("getAgeingSeries", () => fetchJson("/api/debug/ageing"), (r) => validateAgeing(r)),
  getEvidence:       wrap("getEvidence", fetchEvidence, (r) => validateEvidence(r)),
  getApiCatalog:     wrap("getApiCatalog", () => fetchJson("/api/debug/catalog")),
  comparisonMatrix:  wrap("comparisonMatrix", fetchComparisonMatrix),
  
  getDiaryEntries: wrap("getDiaryEntries", () => fetchJson("/api/diary")),
  addDiaryEntry: wrap("addDiaryEntry", (e) => fetchJson("/api/diary", { method: "POST", body: JSON.stringify(e) })),
  updateDiaryEntry: wrap("updateDiaryEntry", (id, u) => fetchJson(`/api/diary/${id}`, { method: "PUT", body: JSON.stringify(u) })),
};
