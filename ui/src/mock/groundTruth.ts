/**
 * Ground-truth calibration anchors.
 *
 * Now sourced from the real `myface/` calibration set (199 portraits, real
 * head-pose annotations). We pick a stratified subset across pose classes
 * so the anchor list always covers every bucket; UI lets the owner refine
 * the expected fields and persists overrides in localStorage.
 *
 * The shape (`GroundTruth`) is preserved for callers (validators, tests,
 * ground-truth page editor).
 */

import { MYFACE_PHOTOS, type RealPhoto } from "../data/photoRegistry";

export interface GroundTruth {
  file: string;
  url: string;
  capturedAt: string;
  year: number;
  month: number;
  day: number;
  expectedPose?: "frontal" | "three_quarter_left" | "three_quarter_right" | "profile_left" | "profile_right";
  expectedExpression?: "neutral" | "smile" | "speech" | "serious";
  expectedCluster?: "A" | "B";
  note?: string;
}

const PER_BUCKET = 8;
const POSES: NonNullable<GroundTruth["expectedPose"]>[] = [
  "frontal",
  "three_quarter_left",
  "three_quarter_right",
  "profile_left",
  "profile_right",
];

function toGT(rp: RealPhoto): GroundTruth {
  return {
    file: rp.file,
    url: rp.url,
    capturedAt: rp.date ?? "unknown",
    year: rp.year ?? 0,
    month: rp.date ? +rp.date.slice(5, 7) : 0,
    day: rp.date ? +rp.date.slice(8, 10) : 0,
    // Pre-fill expected fields with the model's own classification so the
    // editor on Ground-truth page starts from a sensible baseline. Owner
    // overrides whatever is wrong.
    expectedPose: rp.pose.classification === "none" ? undefined : (rp.pose.classification as any),
    expectedExpression: "neutral",
    expectedCluster: "A",
    note: `myface anchor · pose source = ${rp.pose.source}`,
  };
}

// Stratify: take up to PER_BUCKET portraits from each pose class. Photos
// are already sorted by date (when present), so this is deterministic.
const byBucket = new Map<string, RealPhoto[]>();
for (const p of MYFACE_PHOTOS) {
  if (p.pose.source === "none") continue;
  const k = p.pose.classification;
  if (!byBucket.has(k)) byBucket.set(k, []);
  byBucket.get(k)!.push(p);
}

const stratified: RealPhoto[] = [];
for (const pose of POSES) {
  const bucket = byBucket.get(pose) ?? [];
  stratified.push(...bucket.slice(0, PER_BUCKET));
}

export const GROUND_TRUTH: GroundTruth[] = stratified.map(toGT);
