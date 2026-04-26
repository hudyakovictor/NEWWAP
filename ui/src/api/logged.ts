/**
 * Logging + validation middleware wrapped around the raw mock backend.
 * Every method call is timed, every response is run through its validator
 * and any resulting violations are attached to the log entry.
 *
 * Keeping this as a thin wrapper means the actual backend (mock or future
 * HTTP) stays clean and deterministic.
 */

import { mockBackend } from "./mock";
import type { Backend } from "./types";
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
        // Keep it debug-level for normal success to avoid spam; still inspectable in console group.
        log.debug("api", `api:${name}`, `${name} ok`, { args, result, durationMs });
        (log as any).time; // silence unused
      }
      // Always stash duration separately at info level for quick timing table
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
  getTimeline: wrap("getTimeline", mockBackend.getTimeline, (r) => validateTimeline(r)),
  listPhotos:  wrap("listPhotos", mockBackend.listPhotos, (r) => validatePhotoList(r)),
  getPhotoDetail: wrap("getPhotoDetail", mockBackend.getPhotoDetail, (r) => validatePhotoDetail(r)),
  similarPhotos: wrap("similarPhotos", mockBackend.similarPhotos),
  getCalibration: wrap("getCalibration", mockBackend.getCalibration, (r) => validateCalibration(r)),
  photosInBucket: wrap("photosInBucket", mockBackend.photosInBucket),
  listJobs:       wrap("listJobs", mockBackend.listJobs, (r) => validateJobs(r)),
  startJob:       wrap("startJob", mockBackend.startJob),
  listInvestigations: wrap("listInvestigations", mockBackend.listInvestigations),
  upsertInvestigation: wrap("upsertInvestigation", mockBackend.upsertInvestigation),
  deleteInvestigation: wrap("deleteInvestigation", mockBackend.deleteInvestigation),
  listAnomalies:  wrap("listAnomalies", mockBackend.listAnomalies, (r) => validateAnomalies(r)),
  uploadPhotos:   wrap("uploadPhotos", mockBackend.uploadPhotos),

  getPipelineStages: wrap("getPipelineStages", mockBackend.getPipelineStages, (r) => validatePipeline(r)),
  getCacheSummary:   wrap("getCacheSummary", mockBackend.getCacheSummary, (r) => validateCache(r)),
  getAgeingSeries:   wrap("getAgeingSeries", mockBackend.getAgeingSeries, (r) => validateAgeing(r)),
  getEvidence:       wrap("getEvidence", mockBackend.getEvidence, (r) => validateEvidence(r)),
  getApiCatalog:     wrap("getApiCatalog", mockBackend.getApiCatalog),
  comparisonMatrix:  wrap("comparisonMatrix", mockBackend.comparisonMatrix),
};
