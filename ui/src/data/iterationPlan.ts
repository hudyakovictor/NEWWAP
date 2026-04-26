/**
 * Iterative analysis plan: pair the main photo set with a calibration
 * baseline so each step produces a comparable forensic signal.
 *
 * Each iteration is a quartet:
 *   { calibA, calibB, mainEarly, mainLate }
 * where calibA/B is a fixed pair from myface (same person, real ground
 * truth), and mainEarly/mainLate are two main photos drawn to fill the
 * timeline progressively (extremes first, then binary subdivision).
 *
 * The intent: the calibration delta sets a baseline for "same person";
 * the main delta is compared against it to assess divergence.
 */

import { MAIN_PHOTOS, MYFACE_PHOTOS, type RealPhoto } from "./photoRegistry";

export interface PhotoCompare {
  poseDeltaYaw: number | null;
  poseDeltaPitch: number | null;
  poseDeltaRoll: number | null;
  luminanceDelta: number | null;
  redDelta: number | null;
  greenDelta: number | null;
  blueDelta: number | null;
  /** Absolute yaw of the more profile-y of the two photos. Useful as a
   *  pose-similarity gate — pairs whose poses differ a lot are weaker
   *  forensic evidence regardless of metric values. */
  worstAbsYaw: number | null;
}

export function comparePhotos(a: RealPhoto, b: RealPhoto): PhotoCompare {
  const ya = a.pose.yaw ?? null;
  const yb = b.pose.yaw ?? null;
  const pa = a.pose.pitch ?? null;
  const pb = b.pose.pitch ?? null;
  const ra = a.pose.roll ?? null;
  const rb = b.pose.roll ?? null;
  const fa = a.faceStats;
  const fb = b.faceStats;
  const sub = (x: number | null, y: number | null): number | null =>
    x == null || y == null ? null : +(x - y).toFixed(2);
  return {
    poseDeltaYaw: sub(ya, yb),
    poseDeltaPitch: sub(pa, pb),
    poseDeltaRoll: sub(ra, rb),
    luminanceDelta: sub(fa?.meanLum ?? null, fb?.meanLum ?? null),
    redDelta: sub(fa?.meanR ?? null, fb?.meanR ?? null),
    greenDelta: sub(fa?.meanG ?? null, fb?.meanG ?? null),
    blueDelta: sub(fa?.meanB ?? null, fb?.meanB ?? null),
    worstAbsYaw: ya != null && yb != null
      ? +Math.max(Math.abs(ya), Math.abs(yb)).toFixed(1)
      : null,
  };
}

/** Cost-of-fitness for picking a year representative: lower is better.
 *  Prefer frontal photos with bbox + face stats and smallest |yaw|. */
function repCost(p: RealPhoto): number {
  let c = 0;
  if (p.pose.classification !== "frontal") c += 100;
  if (p.faceStats == null) c += 50;
  if (p.pose.source === "none") c += 1000;
  c += Math.abs(p.pose.yaw ?? 90);
  return c;
}

/** Best representative photo of a year, or null if year has no photos. */
export function pickYearRep(year: number): RealPhoto | null {
  const cands = MAIN_PHOTOS.filter((p) => p.year === year);
  if (cands.length === 0) return null;
  return cands.slice().sort((a, b) => repCost(a) - repCost(b))[0];
}

/** Pick a stable calibration pair from myface: two frontal portraits
 *  with similar luminance. The pick is deterministic (same on every
 *  reload) so iteration semantics are repeatable. */
export function pickCalibPair(): { a: RealPhoto; b: RealPhoto } | null {
  const frontal = MYFACE_PHOTOS
    .filter((p) => p.pose.classification === "frontal" && p.faceStats != null)
    .sort((a, b) => Math.abs(a.pose.yaw ?? 0) - Math.abs(b.pose.yaw ?? 0));
  if (frontal.length < 2) return null;
  // Most frontal photo + the next that has similar luminance (within ±15)
  const seed = frontal[0];
  const target = seed.faceStats!.meanLum;
  const partner =
    frontal
      .slice(1)
      .find((p) => Math.abs((p.faceStats!.meanLum ?? 0) - target) < 15) ??
    frontal[1];
  return { a: seed, b: partner };
}

/** Year-pair scheduler: produces a deterministic, ordered list of year
 *  pairs by binary subdivision over [yMin..yMax]. First entry is the
 *  outermost extremes, then quarters, eighths, and so on. */
export function buildYearSchedule(yMin = 1999, yMax = 2025): Array<[number, number]> {
  const out: Array<[number, number]> = [];
  // 1: extremes
  out.push([yMin, yMax]);
  // Subdivide queue
  const queue: Array<[number, number]> = [[yMin, yMax]];
  while (queue.length > 0) {
    const [lo, hi] = queue.shift()!;
    if (hi - lo <= 1) continue;
    const mid = Math.floor((lo + hi) / 2);
    const next: Array<[number, number]> = [
      [lo, mid],
      [mid, hi],
    ];
    for (const p of next) {
      if (!out.some(([a, b]) => a === p[0] && b === p[1])) {
        out.push(p);
        queue.push(p);
      }
    }
  }
  return out;
}

export interface Iteration {
  index: number;
  earlyYear: number;
  lateYear: number;
  calib: { a: RealPhoto; b: RealPhoto };
  early: RealPhoto | null;
  late: RealPhoto | null;
  /** Δ on the calibration pair — baseline for "same person" */
  calibDelta: PhotoCompare;
  /** Δ on the main pair */
  mainDelta: PhotoCompare;
  /** abs(mainΔ - calibΔ) on each component, summarised. Useful as a
   *  quick "how off is the main pair from baseline" heuristic. */
  divergence: PhotoCompare;
}

function diff(a: PhotoCompare, b: PhotoCompare): PhotoCompare {
  const sub = (x: number | null, y: number | null): number | null =>
    x == null || y == null ? null : +Math.abs(x - y).toFixed(2);
  return {
    poseDeltaYaw: sub(a.poseDeltaYaw, b.poseDeltaYaw),
    poseDeltaPitch: sub(a.poseDeltaPitch, b.poseDeltaPitch),
    poseDeltaRoll: sub(a.poseDeltaRoll, b.poseDeltaRoll),
    luminanceDelta: sub(a.luminanceDelta, b.luminanceDelta),
    redDelta: sub(a.redDelta, b.redDelta),
    greenDelta: sub(a.greenDelta, b.greenDelta),
    blueDelta: sub(a.blueDelta, b.blueDelta),
    worstAbsYaw: null,
  };
}

export function buildIterations(yMin = 1999, yMax = 2025): Iteration[] {
  const calib = pickCalibPair();
  if (!calib) return [];
  const calibDelta = comparePhotos(calib.a, calib.b);
  const schedule = buildYearSchedule(yMin, yMax);
  return schedule.map(([early, late], i) => {
    const e = pickYearRep(early);
    const l = pickYearRep(late);
    const mainDelta = e && l ? comparePhotos(e, l) : ({} as PhotoCompare);
    const divergence = e && l ? diff(mainDelta, calibDelta) : ({} as PhotoCompare);
    return {
      index: i + 1,
      earlyYear: early,
      lateYear: late,
      calib,
      early: e,
      late: l,
      calibDelta,
      mainDelta,
      divergence,
    };
  });
}
