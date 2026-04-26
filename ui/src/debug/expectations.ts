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
    skull_ratio:      { min: 1.55, max: 1.90, note: "bone asymmetry ratio (H0 geometric)" } as Range,
    neurocranium_mm:  { min: 129.5, max: 136.5, note: "neurocranium width, frontal-only" } as Range,
    orbital_angle:    { min: 1.5, max: 4.5, note: "orbital asymmetry angle in degrees" } as Range,
    facial_bmi:       { min: 0.35, max: 0.90, note: "tissue deficit index" } as Range,
    synthetic_prob:   { min: 0.0, max: 1.0, note: "synthetic material probability (0..1)" } as Range,
    lbp_complexity:   { min: 0.05, max: 1.0, note: "LBP texture complexity" } as Range,
    estimated_age:    { min: 44, max: 75, note: "estimated age in years across 1999..2025" } as Range,
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
    count:  { min: 21, max: 21, note: "must always be 21 zones" } as Range,
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
    year_coverage: { min: 1999, max: 2026, note: "TZ investigation window (extended to current year)" } as Range,
  },
};

/* -------------------- Validator helpers ------------------------------- */

export function inRange(v: number, r: Range): boolean {
  return v >= r.min && v <= r.max;
}

export function checkRange(
  field: string,
  value: unknown,
  r: Range,
  severity: Violation["severity"] = "warn"
): Violation | null {
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
