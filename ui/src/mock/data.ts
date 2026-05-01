// Mock data for DEEPUTIN timeline UI
//
// ONLY real pipeline data is kept. All PRNG-generated synthetic values
// have been removed — fake numbers mislead the investigator.
//
// Real sources:
//   - photoRegistry: pose (HPE/3DDFA), year, URL
//   - yearStats: per-year aggregates from pose pipeline
//   - yearLuminance: per-year face crop stats from face_stats pipeline
//
// Removed (were PRNG stubs):
//   - 7 synthetic metric rows (skull, neuro, orbital, bmi, synth, lbp, age)
//   - identitySegments (fabricated A/B boundaries)
//   - eventMarkers (fabricated timeline events)
//   - photoVolume PRNG histogram (replaced with real counts)
//   - anomaly/note fields on PhotoPoint (fabricated)
//   - identity field on PhotoPoint (fabricated A/B assignment)

export type Severity = "ok" | "info" | "warn" | "danger";

export interface PhotoPoint {
  /** Unique index in the timeline */
  index: number;
  year: number;
  photo: string; // single photo url
  photoId: string;
  pose: {
    yaw: number | null;
    pitch: number | null;
    classification: string;
    source: string;
  };
  /** anomaly severity — null until real anomaly detection runs */
  anomaly?: Severity | null;
  /** human label — null until real analysis */
  note?: string | null;
  /** identity cluster — null until real bayesian court runs */
  identity: "A" | "B" | string | null;
}

export interface MetricConfig {
  id: string;
  title: string;
  subtitle?: string;
  unit?: string;
  color: string; // hex
  kind: "line" | "bar";
  domain?: [number, number];
  /** value per photo point */
  values: number[];
  /** optional flags per point */
  flags?: (Severity | undefined)[];
  /** whether this metric comes from a real pipeline (true) or is a stub (false) */
  real?: boolean;
}

export interface IdentitySegment {
  id: "A" | "B";
  from: number;
  to: number;
}

export interface EventMarker {
  year: number;
  kind: "calendar" | "info" | "warn" | "danger" | "ok" | "health";
  title: string;
}

// Legacy fallback URLs only used when no real photo is available for a
// given year. Real per-year anchors come from the photo registry below.
import { MAIN_PHOTOS, yearStats, yearLuminance } from "../data/photoRegistry";

// Real per-year aggregates from the head-pose pipeline. Used to power
// the timeline rows that we can honestly produce from the data we have.
const REAL_YEAR_STATS = yearStats(MAIN_PHOTOS);
function realByYear<T>(years: number[], get: (s: { year: number; count: number; meanAbsYaw: number; frontalRatio: number; yawStd: number }) => T, missing: T): T[] {
  return years.map((y) => {
    const s = REAL_YEAR_STATS.find((x) => x.year === y);
    return s ? get(s) : missing;
  });
}

/** Get all photos as individual points, filtered by preferred pose. Each photo = one point. */
function getPhotoPoints(preferredPose?: string): PhotoPoint[] {
  let pool = MAIN_PHOTOS.filter((p) => p.pose.source !== "none");
  
  if (preferredPose) {
    const matching = MAIN_PHOTOS.filter((p) => p.pose.classification === preferredPose);
    if (matching.length > 0) pool = matching;
  }
  
  // Sort by year, then by smallest |yaw| within each year
  pool.sort((a, b) => {
    if (a.year !== b.year) return (a.year ?? 0) - (b.year ?? 0);
    return Math.abs(a.pose.yaw ?? 0) - Math.abs(b.pose.yaw ?? 0);
  });
  
  return pool.map((p, idx) => ({
    index: idx,
    year: p.year ?? 0,
    photo: p.url,
    photoId: p.id,
    pose: {
      yaw: p.pose.yaw,
      pitch: p.pose.pitch,
      classification: p.pose.classification,
      source: p.pose.source,
    },
    anomaly: null,
    identity: null,
    note: null,
  }));
}

// Keep YEARS for year-axis labels
export const YEARS: number[] = [];
for (let y = 1999; y <= 2025; y++) YEARS.push(y);

export function buildPhotoPoints(preferredPose?: string): PhotoPoint[] {
  return getPhotoPoints(preferredPose);
}

export const photoPoints: PhotoPoint[] = buildPhotoPoints();

// Backwards compatibility - export YearPoint as alias to PhotoPoint
export type YearPoint = PhotoPoint;
export const buildYearPoints = buildPhotoPoints;
export const yearPoints = photoPoints;

// REAL metrics from the head-pose pipeline aggregates.
const realPhotoCount = realByYear(YEARS, (s) => s.count, 0);
const realMeanAbsYaw = realByYear(YEARS, (s) => s.meanAbsYaw, 0);
const realFrontalRatio = realByYear(YEARS, (s) => s.frontalRatio, 0);

// REAL face-crop luminance per year (from face_stats pipeline).
const REAL_LUM = yearLuminance(MAIN_PHOTOS);
const realMeanLum = YEARS.map((y) => REAL_LUM.find((s) => s.year === y)?.meanLum ?? 0);
const realStdLum = YEARS.map((y) => REAL_LUM.find((s) => s.year === y)?.stdLum ?? 0);

export const metrics: MetricConfig[] = [
  // === REAL metrics only ===
  {
    id: "real_count",
    title: "Фотографий / год (реальные)",
    subtitle: "основная папка",
    color: "#22c55e",
    kind: "bar",
    domain: [0, Math.max(1, ...realPhotoCount)],
    values: realPhotoCount,
    real: true,
  },
  {
    id: "real_yaw",
    title: "Средний |рыск| / год (реальный)",
    unit: "°",
    subtitle: "pipeline ракурса",
    color: "#38bdf8",
    kind: "line",
    domain: [0, Math.max(1, ...realMeanAbsYaw)],
    values: realMeanAbsYaw,
    real: true,
  },
  {
    id: "real_frontal",
    title: "Доля фронтальных / год (реальная)",
    subtitle: "фронтальные среди всех",
    color: "#a855f7",
    kind: "line",
    domain: [0, 1],
    values: realFrontalRatio,
    real: true,
  },
  {
    id: "real_lum",
    title: "Средняя яркость лица / год (реальная)",
    subtitle: "ITU-R BT.601, кроп лица",
    color: "#eab308",
    kind: "line",
    domain: [Math.max(0, Math.min(...realMeanLum.filter((x) => x > 0))) - 5, Math.max(...realMeanLum) + 5],
    values: realMeanLum,
    real: true,
  },
  {
    id: "real_lum_std",
    title: "σ яркости лица / год (реальная)",
    subtitle: "разброс внутри года",
    color: "#eab308",
    kind: "bar",
    domain: [0, Math.max(...realStdLum) || 1],
    values: realStdLum,
    real: true,
  },
];

// No real identity segments exist — bayesian court has not run.
export const identitySegments: IdentitySegment[] = [];

// No real event markers exist — these were fabricated.
export const eventMarkers: EventMarker[] = [];

// Real photo volume per year (from actual photo counts), not PRNG.
export const photoVolume: number[] = realPhotoCount;
