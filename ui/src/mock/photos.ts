/**
 * Photo registry exposed to legacy UI consumers.
 *
 * Source of truth = real pose data in `src/data/photoRegistry.ts`. Every
 * PhotoRecord here points at a real file on disk (under
 * `ui/public/photos_main/` or `ui/public/photos_myface/`) and carries a
 * REAL pose classification.
 *
 * Fields that have NOT yet been derived from a real pipeline run
 * (synthetic-material probability, bayesian posteriors, identity cluster,
 * texture flags, md5, resolution, expression, source-of-photo) are set
 * to **null** — not fake values.  The UI must handle null explicitly
 * and show "нет данных" rather than a misleading number.
 *
 * When a real pipeline computes any of these fields, replace the null
 * with the real value and remove the field from NULL_FIELDS.
 */

import { ALL_PHOTOS, type RealPhoto, type PoseClassification } from "../data/photoRegistry";
import forensicRegistryRaw from "../data/forensic_registry.json";

const FORENSIC_REGISTRY = forensicRegistryRaw as Record<string, any>;

export type PoseEnum = PoseClassification;

/** Per-record list of fields that are still null (no real pipeline output). */
export const NULL_FIELDS = [
  "expression",
  "source",
  "resolution",
  "flags",
  "syntheticProb",
  "bayesH0",
  "cluster",
  "md5",
] as const;

export interface PhotoRecord {
  id: string;
  /** Year parsed from filename, or 0 when the filename doesn't encode a date. */
  year: number;
  /** YYYY-MM-DD when filename encodes it, else "" */
  date: string;
  /** Real, public URL of the file. */
  photo: string;
  /** REAL pose classification from the head-pose pipeline. */
  pose: PoseEnum;
  /** REAL yaw in degrees (null when pose detection failed). */
  yaw: number | null;
  /** REAL pose source: "hpe" primary, "3ddfa" fallback, "none" if both failed. */
  poseSource: "hpe" | "3ddfa" | "none";
  /** Folder this photo was loaded from. Real. */
  folder: "main" | "myface";

  /* === fields below are null until their real pipeline runs === */
  expression: string | null;
  source: string | null;
  resolution: string | null;
  flags: string[];
  syntheticProb: number | null;
  bayesH0: number | null;
  cluster: string | null;
  md5: string | null;
}

function recordFromRealPhoto(rp: RealPhoto): PhotoRecord {
  const base: PhotoRecord = {
    id: rp.id,
    year: rp.year ?? 0,
    date: rp.date ?? "",
    photo: rp.url,
    pose: rp.pose.classification,
    yaw: rp.pose.yaw,
    poseSource: rp.pose.source,
    folder: rp.folder,

    // All stubs removed — null until real pipeline computes them
    expression: null,
    source: null,
    resolution: null,
    flags: [],
    syntheticProb: null,
    bayesH0: null,
    cluster: null,
    md5: null,
  };

  // Check for deep forensic analysis results (forensic_registry)
  // These are the ONLY source of real non-null values for these fields.
  const real = FORENSIC_REGISTRY[rp.id];
  if (real) {
    if (real.md5) base.md5 = real.md5;
    if (real.resolution) base.resolution = real.resolution;
    if (typeof real.syntheticProb === "number") base.syntheticProb = real.syntheticProb;
    if (real.source) base.source = real.source;

    // Rule-based flags from real metrics only
    if (real.syntheticProb > 0.45) base.flags.push("silicone");
  }

  // Pose fallback flag is real data, not a stub
  if (rp.pose.source === "3ddfa") base.flags.push("pose_fallback");

  return base;
}

export const PHOTOS: PhotoRecord[] = ALL_PHOTOS.map(recordFromRealPhoto);
