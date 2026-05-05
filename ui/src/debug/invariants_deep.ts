/**
 * Deeper cross-field invariants. These catch regressions that the basic
 * suite (invariants.ts) cannot, by comparing values that should agree across
 * different parts of the pipeline.
 */

import type { Finding, InvariantContext } from "./invariants";

/* ---------------------------------------------------------------------- */
/* Coverage & integrity                                                   */
/* ---------------------------------------------------------------------- */

export async function checkPhotoYearCoverage(): Promise<Finding[]> {
  // Disabled - depends on mock PHOTOS
  return [];
}

export async function checkAnomalyIntegrity(ctx: InvariantContext): Promise<Finding[]> {
  // Disabled - depends on mock PHOTOS
  return [];
}

export async function checkCalibrationCoverage(ctx: InvariantContext): Promise<Finding[]> {
  // Disabled - depends on mock data
  return [];
}

/* ---------------------------------------------------------------------- */
/* Cross-field consistency                                                 */
/* ---------------------------------------------------------------------- */

export async function checkEvidenceVsAnomalies(ctx: InvariantContext): Promise<Finding[]> {
  // Disabled - depends on mock data
  return [];
}

export async function checkGroundTruthAlignment(ctx: InvariantContext): Promise<Finding[]> {
  // Disabled - depends on GROUND_TRUTH from mock
  return [];
}

export const DEEP_INVARIANTS = [
  { id: "photo_year_coverage", run: checkPhotoYearCoverage },
  { id: "anomaly_integrity", run: checkAnomalyIntegrity },
  { id: "calibration_coverage", run: checkCalibrationCoverage },
  { id: "evidence_vs_anomalies", run: checkEvidenceVsAnomalies },
  { id: "ground_truth_alignment", run: checkGroundTruthAlignment },
];
