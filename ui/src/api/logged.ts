/**
 * Logging + validation middleware wrapped around the HTTP backend.
 * Every method call is timed, every response is run through its validator
 * and any resulting violations are attached to the log entry.
 */

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

const API_BASE = "http://localhost:8011";

async function fetchJson(path: string, options: RequestInit = {}) {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    signal: AbortSignal.timeout(10000), // 10s global timeout
  });
  if (!resp.ok) throw new Error(`Backend error: ${resp.statusText}`);
  return resp.json();
}

async function fetchEvidence(aId: string, bId: string): Promise<EvidenceBreakdown> {
  return await fetchJson(`/api/evidence/compare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ photo_id_a: aId, photo_id_b: bId }),
  });
}

async function fetchComparisonMatrix(ids: string[]): Promise<number[][]> {
  return await fetchJson(`/api/evidence/matrix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(ids),
  });
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
  listPhotos:  wrap("listPhotos", (q) => {
    const params = new URLSearchParams();
    if (q) {
      if (q.pose) params.set("pose", q.pose);
      if (q.expression) params.set("expression", q.expression);
      if (q.source) params.set("source", q.source);
      if (q.flag) params.set("flag", q.flag);
      if (q.minSyntheticProb != null) params.set("minSyntheticProb", String(q.minSyntheticProb));
      if (q.search) params.set("search", q.search);
      if (q.sortBy) params.set("sortBy", q.sortBy);
      if (q.limit) params.set("limit", String(q.limit));
      if (q.offset) params.set("offset", String(q.offset));
    }
    const qs = params.toString();
    return fetchJson(`/api/photos/main${qs ? `?${qs}` : ""}`);
  }, (r) => validatePhotoList(r)),
  getPhotoDetail: wrap("getPhotoDetail", (id) => fetchJson(`/api/photo/main/${id}`), (r) => validatePhotoDetail(r)),
  similarPhotos: wrap("similarPhotos", (id) => fetchJson(`/api/similar-photos/${id}`)),
  getCalibration: wrap("getCalibration", () => fetchJson("/api/calibration/summary"), (r) => validateCalibration(r)),
  photosInBucket: wrap("photosInBucket", (p, l) => fetchJson(`/api/photos-in-bucket?pose=${encodeURIComponent(p)}&light=${encodeURIComponent(l)}`)),
  listJobs:       wrap("listJobs", () => fetchJson("/api/jobs"), (r) => validateJobs(r)),
  startJob:       wrap("startJob", (kind) => {
    const endpoint = kind === "extract" ? "extract"
      : kind === "recompute-metrics" ? "recompute-metrics"
      : kind === "calibrate" ? "recompute-metrics"  // calibrate maps to recompute with metric_keys
      : "recompute-metrics";  // reindex also maps to recompute for now
    return fetchJson(`/api/jobs/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset: "main", limit: 100, metric_keys: kind === "calibrate" ? ["calibration"] : undefined }),
    });
  }),
  listInvestigations: wrap("listInvestigations", () => fetchJson("/api/investigations")),
  upsertInvestigation: wrap("upsertInvestigation", (inv) => fetchJson("/api/investigations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(inv),
  })),
  deleteInvestigation: wrap("deleteInvestigation", (id) => fetchJson(`/api/investigations/${id}`, { method: "DELETE" })),
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
  addDiaryEntry: wrap("addDiaryEntry", (e) => fetchJson("/api/diary", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(e),
  })),
  updateDiaryEntry: wrap("updateDiaryEntry", (id, u) => fetchJson(`/api/diary/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(u),
  })),
};
