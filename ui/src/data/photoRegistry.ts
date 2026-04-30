/**
 * Real photo registry. Replaces the synthetic generator in `src/mock/photos.ts`.
 *
 * Source of truth = the consolidated pose JSONs produced by
 * `scripts/poses_hpe_safe.py` and `scripts/poses_3ddfa_safe.py`. Those JSONs
 * are bundled into the build via direct JSON imports below.
 *
 * Real fields per photo:
 *   - file, url, year (parsed from "YYYY_MM_DD…" filename when present)
 *   - pose (yaw, pitch, roll, source, classification)
 * Other fields (cluster / syntheticProb / bayesH0 / flags / md5 / dhash)
 * are NOT real yet — those need their own pipeline runs. They are exposed
 * here as `null` so the UI can mark them as "stub" rather than fabricate
 * fake values.
 */

import mainPosesRaw from "./poses_main.json";
import myfacePosesRaw from "./poses_myface.json";
import mainFaceStatsRaw from "./face_stats_main.json";
import myfaceFaceStatsRaw from "./face_stats_myface.json";

interface FaceStats {
  meanLum: number;
  stdLum: number;
  meanR: number;
  meanG: number;
  meanB: number;
  stdR: number;
  stdG: number;
  stdB: number;
  cropW: number;
  cropH: number;
}
const FACE_STATS_MAIN = mainFaceStatsRaw as Record<string, FaceStats | null>;
const FACE_STATS_MYFACE = myfaceFaceStatsRaw as Record<string, FaceStats | null>;

export type PoseClassification =
  | "frontal"
  | "three_quarter_left"
  | "three_quarter_right"
  | "profile_left"
  | "profile_right"
  | "none";

export interface PoseEntry {
  yaw: number | null;
  pitch: number | null;
  roll: number | null;
  source: "hpe" | "3ddfa" | "none";
  classification: PoseClassification;
}

export interface RealPhoto {
  /** Stable id derived from the filename (without extension). */
  id: string;
  /** Filename including extension. */
  file: string;
  /** Public URL the dev/prod server serves it from. */
  url: string;
  /** Folder this photo belongs to. */
  folder: "main" | "myface";
  /** Year parsed from the filename if it starts with YYYY_. Otherwise null. */
  year: number | null;
  /** Date string YYYY-MM-DD if filename gives full date, else null. */
  date: string | null;
  pose: PoseEntry;
  /** Real face crop stats from face_stats pipeline (null when SCRFD missed). */
  faceStats: FaceStats | null;
}

const FILENAME_DATE = /^(\d{4})[_-](\d{2})[_-](\d{2})/;

function parseDate(file: string): { year: number | null; date: string | null } {
  const m = FILENAME_DATE.exec(file);
  if (!m) return { year: null, date: null };
  return { year: +m[1], date: `${m[1]}-${m[2]}-${m[3]}` };
}

function build(folder: "main" | "myface", raw: Record<string, any>, urlPrefix: string): RealPhoto[] {
  const stats = folder === "main" ? FACE_STATS_MAIN : FACE_STATS_MYFACE;
  const out: RealPhoto[] = [];
  const excludedFiles = new Set([
    "2020_02_27.jpg",
    "2025_03_25.jpg",
    "Снимок экрана 2026-04-09 в 21.06.11.png",
    "Снимок экрана 2026-04-09 в 21.10.01.png",
    "Снимок экрана 2026-04-09 в 21.10.07.png",
  ]);
  for (const [file, entry] of Object.entries(raw)) {
    if (excludedFiles.has(file)) continue;
    const { year, date } = parseDate(file);
    // Include extension in id to avoid collisions like 1.jpg vs 1.png.
    const id = `${folder}-${file}`;
    out.push({
      id,
      file,
      url: `${urlPrefix}/${encodeURIComponent(file)}`,
      folder,
      year,
      date,
      pose: {
        yaw: entry?.yaw ?? null,
        pitch: entry?.pitch ?? null,
        roll: entry?.roll ?? null,
        source: entry?.source ?? "none",
        classification: entry?.classification ?? "none",
      },
      faceStats: stats[file] ?? null,
    });
  }
  // Sort by date when available so timeline-like consumers get a stable order.
  out.sort((a, b) => {
    if (a.date && b.date) return a.date.localeCompare(b.date);
    if (a.date) return -1;
    if (b.date) return 1;
    return a.file.localeCompare(b.file);
  });
  return out;
}

export const MAIN_PHOTOS: RealPhoto[] = build(
  "main",
  mainPosesRaw as Record<string, any>,
  "/photos_main"
);
export const MYFACE_PHOTOS: RealPhoto[] = build(
  "myface",
  myfacePosesRaw as Record<string, any>,
  "/photos_myface"
);

export const ALL_PHOTOS: RealPhoto[] = [...MAIN_PHOTOS, ...MYFACE_PHOTOS];

export function poseDistribution(photos: RealPhoto[]): Record<PoseClassification, number> {
  const out: Record<PoseClassification, number> = {
    frontal: 0,
    three_quarter_left: 0,
    three_quarter_right: 0,
    profile_left: 0,
    profile_right: 0,
    none: 0,
  };
  for (const p of photos) out[p.pose.classification]++;
  return out;
}

export function sourceDistribution(photos: RealPhoto[]): Record<"hpe" | "3ddfa" | "none", number> {
  const out = { hpe: 0, "3ddfa": 0, none: 0 } as Record<"hpe" | "3ddfa" | "none", number>;
  for (const p of photos) out[p.pose.source]++;
  return out;
}

export interface YearStat {
  year: number;
  count: number;
  meanAbsYaw: number;
  meanAbsPitch: number;
  meanAbsRoll: number;
  frontalCount: number;
  /** fraction of photos that classified as frontal */
  frontalRatio: number;
  /** spread of yaw values, robust to outliers */
  yawStd: number;
}

export interface YearLuminance {
  year: number;
  count: number;
  meanLum: number;
  stdLum: number;
}

export function yearLuminance(photos: RealPhoto[]): YearLuminance[] {
  const byYear = new Map<number, FaceStats[]>();
  for (const p of photos) {
    if (p.year == null || p.faceStats == null) continue;
    if (!byYear.has(p.year)) byYear.set(p.year, []);
    byYear.get(p.year)!.push(p.faceStats);
  }
  const out: YearLuminance[] = [];
  for (const [year, list] of byYear) {
    const lums = list.map((s) => s.meanLum);
    const m = lums.reduce((a, x) => a + x, 0) / Math.max(1, lums.length);
    const v = lums.reduce((a, x) => a + (x - m) ** 2, 0) / Math.max(1, lums.length);
    out.push({ year, count: list.length, meanLum: +m.toFixed(1), stdLum: +Math.sqrt(v).toFixed(1) });
  }
  out.sort((a, b) => a.year - b.year);
  return out;
}

/** Aggregate per-year pose statistics over photos that have a parseable
 *  year in their filename and a real pose entry (HPE or 3DDFA). Returns
 *  one entry per year covered by the photo set. */
export function yearStats(photos: RealPhoto[]): YearStat[] {
  const byYear = new Map<number, RealPhoto[]>();
  for (const p of photos) {
    if (p.year == null) continue;
    if (p.pose.source === "none") continue;
    if (!byYear.has(p.year)) byYear.set(p.year, []);
    byYear.get(p.year)!.push(p);
  }
  const out: YearStat[] = [];
  for (const [year, list] of byYear) {
    const yaws = list.map((p) => p.pose.yaw ?? 0);
    const pitches = list.map((p) => p.pose.pitch ?? 0);
    const rolls = list.map((p) => p.pose.roll ?? 0);
    const meanAbs = (arr: number[]) => arr.reduce((a, x) => a + Math.abs(x), 0) / Math.max(1, arr.length);
    const meanY = yaws.reduce((a, x) => a + x, 0) / Math.max(1, yaws.length);
    const yawStd = Math.sqrt(yaws.reduce((a, x) => a + (x - meanY) ** 2, 0) / Math.max(1, yaws.length));
    const frontalCount = list.filter((p) => p.pose.classification === "frontal").length;
    out.push({
      year,
      count: list.length,
      meanAbsYaw: +meanAbs(yaws).toFixed(2),
      meanAbsPitch: +meanAbs(pitches).toFixed(2),
      meanAbsRoll: +meanAbs(rolls).toFixed(2),
      frontalCount,
      frontalRatio: +(frontalCount / list.length).toFixed(3),
      yawStd: +yawStd.toFixed(2),
    });
  }
  out.sort((a, b) => a.year - b.year);
  return out;
}
