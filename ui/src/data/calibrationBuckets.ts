/**
 * Real calibration buckets derived from myface same-person pairs.
 *
 * Source: storage/myface_pairs.json
 * Computes per-bucket metrics: count, variance, level (unreliable/low/medium/high)
 *
 * Exported: getCalibrationBuckets() for use in mock.ts
 */

import pairsRaw from "../../storage/myface_pairs.json";

interface Pair {
  a: string;
  b: string;
  person: string;
  deltaYaw: number;
  poseA: string;
  poseB: string;
  lightCategory: string;
  bucketKey: string;
}

interface PairsFile {
  generatedAt: string;
  maxYawDelta: number;
  maxPerBucket: number;
  totalPairs: number;
  byPerson: Record<string, number>;
  byBucket: Record<string, number>;
  pairs: Pair[];
}

const PAIRS = pairsRaw as PairsFile;

export type CalibrationLevel = "unreliable" | "low" | "medium" | "high";

export interface CalibrationBucket {
  pose: string;
  light: string;
  level: CalibrationLevel;
  count: number;
  variance: number; // Simulated for now, will be real once we have zone scores
  personDistribution: Record<string, number>; // personA vs personB counts
}

export interface CalibrationHealth {
  bucketCount: number;
  confidenceBucketCounts: {
    unreliable: number;
    low: number;
    medium: number;
    high: number;
  };
  unusableBuckets: string[];
  lowConfidenceBuckets: string[];
  readyForRuntimeBucketKeys: string[];
  trustedBucketCount: number;
  usableBucketCount: number;
}

function getLevelFromCount(count: number): CalibrationLevel {
  if (count < 5) return "unreliable";
  if (count < 15) return "low";
  if (count < 30) return "medium";
  return "high";
}

/**
 * Build calibration buckets from myface pairs.
 * Each unique pose+light combo becomes a bucket.
 */
export function buildCalibrationBuckets(): CalibrationBucket[] {
  const buckets = new Map<string, { pose: string; light: string; count: number; persons: Map<string, number> }>();

  const EXPECTED_POSES = ["frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right"];
  const EXPECTED_LIGHTS = ["daylight", "studio", "low_light", "mixed", "flash"];
  for (const p of EXPECTED_POSES) {
    for (const l of EXPECTED_LIGHTS) {
      buckets.set(`${p}:::${l}`, { pose: p, light: l, count: 0, persons: new Map() });
    }
  }

  for (const pair of PAIRS.pairs) {
    const key = `${pair.poseA}:::${pair.lightCategory}`;
    if (!buckets.has(key)) {
      buckets.set(key, { pose: pair.poseA, light: pair.lightCategory, count: 0, persons: new Map() });
    }
    const bucket = buckets.get(key)!;
    bucket.count++;
    bucket.persons.set(pair.person, (bucket.persons.get(pair.person) || 0) + 1);
  }

  const result: CalibrationBucket[] = [];

  for (const [, data] of buckets) {
    const { pose, light } = data;
    const personDistribution: Record<string, number> = {};
    for (const [person, count] of data.persons) {
      personDistribution[person] = count;
    }

    result.push({
      pose,
      light,
      level: getLevelFromCount(data.count),
      count: data.count,
      variance: 0.15 + Math.random() * 0.1, // Placeholder until real zone scores
      personDistribution,
    });
  }

  // Sort by count descending
  return result.sort((a, b) => b.count - a.count);
}

/**
 * Compute calibration health metrics for diagnostics.
 */
export function buildCalibrationHealth(): CalibrationHealth {
  const buckets = buildCalibrationBuckets();

  const counts = {
    unreliable: buckets.filter((b) => b.level === "unreliable").length,
    low: buckets.filter((b) => b.level === "low").length,
    medium: buckets.filter((b) => b.level === "medium").length,
    high: buckets.filter((b) => b.level === "high").length,
  };

  const unusableBuckets = buckets
    .filter((b) => b.level === "unreliable")
    .map((b) => `${b.pose}_${b.light}`);

  const lowConfidenceBuckets = buckets
    .filter((b) => b.level === "low")
    .map((b) => `${b.pose}_${b.light}`);

  const readyForRuntime = buckets
    .filter((b) => b.level === "medium" || b.level === "high")
    .map((b) => `${b.pose}_${b.light}`);

  return {
    bucketCount: buckets.length,
    confidenceBucketCounts: counts,
    unusableBuckets,
    lowConfidenceBuckets,
    readyForRuntimeBucketKeys: readyForRuntime,
    trustedBucketCount: counts.high,
    usableBucketCount: counts.medium + counts.high,
  };
}

/**
 * Get bucket key for a pair of photos based on their poses and light.
 * Used by PairAnalysis to check calibration health.
 */
export function getBucketKeyForPair(
  poseA: string,
  _poseB: string,
  lightA: string
): string {
  // Use the more restrictive pose (less common one)
  // For simplicity, just use poseA with lightA
  return `${poseA}_${lightA}`;
}

/**
 * Check if a bucket is ready for runtime use.
 */
export function isBucketReady(pose: string, light: string): boolean {
  const buckets = buildCalibrationBuckets();
  const bucket = buckets.find((b) => b.pose === pose && b.light === light);
  if (!bucket) return false;
  return bucket.level === "medium" || bucket.level === "high";
}

/**
 * Get fallback policy for a bucket based on its health.
 */
export function getBucketFallbackPolicy(
  pose: string,
  light: string
): {
  ready: boolean;
  mode: "strict" | "conservative" | "normal";
  confidence: number;
} {
  const buckets = buildCalibrationBuckets();
  const bucket = buckets.find((b) => b.pose === pose && b.light === light);

  if (!bucket) {
    return { ready: false, mode: "strict", confidence: 0 };
  }

  switch (bucket.level) {
    case "high":
      return { ready: true, mode: "normal", confidence: 0.9 };
    case "medium":
      return { ready: true, mode: "conservative", confidence: 0.7 };
    case "low":
      return { ready: false, mode: "conservative", confidence: 0.5 };
    case "unreliable":
    default:
      return { ready: false, mode: "strict", confidence: 0.3 };
  }
}
