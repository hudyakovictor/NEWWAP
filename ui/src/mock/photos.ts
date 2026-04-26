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
 * texture flags, md5, resolution, expression, source-of-photo) are filled
 * with deterministic stub values so the existing UI keeps rendering.
 * They are marked via the `stubFields` array and via UI banners on pages
 * that still depend on them.
 *
 * Once a real pipeline computes any of these fields, drop the field from
 * `STUB_FIELDS` and have the registry return the real value.
 */

import { ALL_PHOTOS, type RealPhoto, type PoseClassification } from "../data/photoRegistry";
import { rngFor } from "../debug/prng";

export type PoseEnum = PoseClassification;
export type ExprEnum = "neutral" | "smile" | "speech" | "serious" | "unknown";
export type SourceEnum = "archival_scan" | "press_photo" | "digital" | "video_frame" | "real_dataset";
export type FlagId =
  | "anomaly"
  | "silicone"
  | "chrono"
  | "cluster_b"
  | "pose_fallback"
  | "low_cal";

/** Per-record list of fields that are not yet derived from a real pipeline. */
export const STUB_FIELDS = [
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

  /* === fields below are stubs until their real pipeline runs === */
  expression: ExprEnum;
  source: SourceEnum;
  resolution: string;
  flags: FlagId[];
  syntheticProb: number;
  bayesH0: number;
  cluster: "A" | "B";
  md5: string;
}

function stubFromRealPhoto(rp: RealPhoto): PhotoRecord {
  // Deterministic stubs derived from id so the same photo always gets the
  // same stub values. This is purely cosmetic — these fields are NOT real.
  const r = rngFor("stub", rp.id);

  const year = rp.year ?? 0;
  // Cluster heuristic = same as previous mock: 2015..2020 → "B", else "A".
  // Still a stub, but matches the existing UI semantics.
  const cluster: "A" | "B" = year >= 2015 && year <= 2020 ? "B" : "A";

  const synthBase = year === 2012 || year === 2014 || year === 2023 ? 0.5 + r() * 0.3 : 0.1 + r() * 0.2;
  const syntheticProb = +Math.min(0.95, synthBase).toFixed(2);
  const bayesH0 = +(cluster === "B" ? 0.25 + r() * 0.2 : 0.6 + r() * 0.25).toFixed(2);

  const flags: FlagId[] = [];
  if (syntheticProb > 0.5) flags.push("silicone");
  if (year === 2012 || year === 2014 || year === 2023) flags.push("anomaly");
  if (cluster === "B") flags.push("cluster_b");
  if (rp.pose.source === "3ddfa") flags.push("pose_fallback");

  return {
    id: rp.id,
    year,
    date: rp.date ?? "",
    photo: rp.url,
    pose: rp.pose.classification,
    yaw: rp.pose.yaw,
    poseSource: rp.pose.source,
    folder: rp.folder,

    expression: "unknown",
    source: "real_dataset",
    resolution: "",
    flags,
    syntheticProb,
    bayesH0,
    cluster,
    md5: "",
  };
}

export const PHOTOS: PhotoRecord[] = ALL_PHOTOS.map(stubFromRealPhoto);
