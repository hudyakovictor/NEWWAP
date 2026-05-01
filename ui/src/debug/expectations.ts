/**
 * Predicted value ranges for every significant data point the pipeline
 * produces. If observed values fall outside these, the validator flags the
 * entry as suspicious so we can audit why.
 *
 * These ranges come from:
 *  - the algorithmic description in the TZ ("about platform.txt")
 *  - physical/physiological plausibility (aging rates, angles, distances)
 *  - properties of the mock generator we wrote in src/mock/*
 *
 * When behaviour legitimately shifts, update the expectation here in one
 * place rather than silencing the log entry.
 */

import type { Violation } from "./logger";

export interface Range {
  min: number;
  max: number;
  note?: string;
}

export const EXPECT = {
  /* --------- Timeline metrics ------------------------------------------ */
  metric: {
    cranial_face_index: { min: 0.5, max: 2.0, note: "cranial-face index ratio" } as Range,
    jaw_width_ratio:    { min: 0.1, max: 1.0, note: "jaw width normalized ratio" } as Range,
    canthal_tilt_L:     { min: -15, max: 25, note: "left canthal angle in degrees" } as Range,
    canthal_tilt_R:     { min: -15, max: 25, note: "right canthal angle in degrees" } as Range,
    nose_projection_ratio: { min: 0.1, max: 0.8, note: "nose projection ratio" } as Range,
    orbit_depth_L_ratio:   { min: 0.05, max: 0.6, note: "left orbit depth ratio" } as Range,
    orbit_depth_R_ratio:   { min: 0.05, max: 0.6, note: "right orbit depth ratio" } as Range,
    texture_silicone_prob:  { min: 0.0, max: 1.0, note: "synthetic material probability (0..1)" } as Range,
    texture_pore_density:   { min: 0.0, max: 1.0, note: "pore density index" } as Range,
    texture_global_smoothness: { min: 0.0, max: 1.0, note: "global smoothness index" } as Range,
    // Timeline aggregate metrics
    photo_count:    { min: 0, max: 200, note: "photos per year" } as Range,
    mean_yaw:       { min: 0, max: 90, note: "mean |yaw| in degrees" } as Range,
    frontal_ratio:  { min: 0, max: 100, note: "frontal ratio in percent" } as Range,
    estimated_age:  { min: 0, max: 120, note: "biological age model" } as Range,
  },

  /* --------- Pose / expression ----------------------------------------- */
  pose: {
    yaw_deg:   { min: -90, max: 90 } as Range,
    pitch_deg: { min: -60, max: 60 } as Range,
    roll_deg:  { min: -45, max: 45 } as Range,
    confidence: { min: 0.5, max: 1.0, note: "pose detector confidence (<0.5 → fallback)" } as Range,
  },
  expression: {
    smile:    { min: 0, max: 1 } as Range,
    jaw_open: { min: 0, max: 1 } as Range,
  },

  /* --------- 21 zones --------------------------------------------------- */
  zone: {
    weight: { min: 0.0, max: 1.0, note: "per-zone weight" } as Range,
    score:  { min: 0.0, max: 1.0, note: "per-zone similarity score" } as Range,
    count:  { min: 18, max: 21, note: "21 minus expression-excluded zones" } as Range,
  },

  /* --------- Bayesian --------------------------------------------------- */
  bayes: {
    prior_sum_min: 0.99,
    prior_sum_max: 1.01,
    posterior_sum_min: 0.99,
    posterior_sum_max: 1.01,
    H0_typical_min: 0.25, // for a genuinely normal pair
    H1_suspicion_threshold: 0.35,
    H2_max_normal: 0.4,
  },

  /* --------- Chronology ageing ----------------------------------------- */
  ageing: {
    residual_normal: { min: -2, max: 2, note: "residual within normal aging ±2σ" } as Range,
    year_range:      { min: 1999, max: 2025 } as Range,
    outlier_count:   { min: 0, max: 8, note: "expect few outliers; many outliers → investigate model" } as Range,
  },

  /* --------- Pipeline --------------------------------------------------- */
  pipeline: {
    stage_drop_pct_max: 5,     // warn if a stage drops >5% of items
    avg_ms_warn_threshold: 600, // warn if any stage exceeds this
    gpu_mb_budget: 4096,
    total_photos_expected: { min: 1500, max: 1900, note: "expect ~1700 photos per TZ" } as Range,
  },

  /* --------- Cache ------------------------------------------------------ */
  cache: {
    vram_budget_mb: 4096,
    vram_warn_ratio: 0.8,
    max_entries: 10,
  },

  /* --------- Calibration ------------------------------------------------ */
  calibration: {
    unreliable_buckets_max: 5,
    high_buckets_min: 3,
  },

  /* --------- Misc ------------------------------------------------------- */
  misc: {
    year_coverage: { min: 1999, max: 2025, note: "TZ investigation window" } as Range,
  },
};

/* -------------------- Validator helpers ------------------------------- */

export function inRange(v: number, r: Range): boolean {
  if (!r) return false;
  return v >= r.min && v <= r.max;
}

export function checkRange(
  field: string,
  value: unknown,
  r: Range,
  severity: Violation["severity"] = "warn"
): Violation | null {
  if (!r) {
    return { field, expected: "defined range", actual: "undefined range", severity: "warn", note: "No expectation defined for this field" };
  }
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return { field, expected: `number in [${r.min}, ${r.max}]`, actual: value, severity: "danger", note: r.note };
  }
  if (inRange(value, r)) return null;
  return {
    field,
    expected: `${r.min}..${r.max}${r.note ? " · " + r.note : ""}`,
    actual: value,
    severity,
  };
}

export function checkSum(
  field: string,
  values: number[],
  min: number,
  max: number
): Violation | null {
  const s = values.reduce((a, b) => a + b, 0);
  if (s >= min && s <= max) return null;
  return {
    field,
    expected: `sum in [${min}, ${max}]`,
    actual: s,
    severity: "danger",
  };
}
