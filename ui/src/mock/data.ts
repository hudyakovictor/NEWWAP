// Mock data for DEEPUTIN timeline UI
// All data here is fake and used purely to drive the interface.

export type Severity = "ok" | "info" | "warn" | "danger";

export interface YearPoint {
  year: number;
  photo: string; // url
  /** main anomaly severity for the marker under the photo */
  anomaly?: Severity;
  /** human label for tooltip */
  note?: string;
  /** identity cluster detected by bayesian courtroom: A = real, B = double */
  identity: "A" | "B";
}

export interface MetricConfig {
  id: string;
  title: string;
  subtitle?: string;
  unit?: string;
  color: string; // hex
  kind: "line" | "bar";
  domain?: [number, number];
  /** value per year */
  values: number[];
  /** optional flags per year (warn/danger emitted as icons under the value) */
  flags?: (Severity | undefined)[];
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

/** For each year in YEARS, return the URL of the most "neutral" real photo
 *  (frontal pose, smallest |yaw|). Falls back to any photo of that year. */
function pickAnchor(year: number): string {
  const candidates = MAIN_PHOTOS.filter((p) => p.year === year && p.pose.source !== "none");
  if (candidates.length === 0) {
    // last resort: any photo of that year, even without pose
    const any = MAIN_PHOTOS.find((p) => p.year === year);
    return any?.url ?? "";
  }
  // prefer frontal, then smallest |yaw|
  const frontal = candidates.filter((p) => p.pose.classification === "frontal");
  const pool = frontal.length > 0 ? frontal : candidates;
  pool.sort((a, b) => Math.abs(a.pose.yaw ?? 0) - Math.abs(b.pose.yaw ?? 0));
  return pool[0].url;
}

const PHOTO_POOL = [
  "/photos/2010_12_16.jpg",
  "/photos/2011_04_14.jpg",
  "/photos/2011_04_21.jpg",
  "/photos/2012_07_30.jpg",
  "/photos/2014_05_20.jpg",
  "/photos/2014_06_09.jpg",
  "/photos/2015_07_14.jpg",
  "/photos/2015_09_03.jpg",
  "/photos/2018_08_03.jpg",
  "/photos/2018_09_08.jpg",
  "/photos/2018_09_18.jpg",
  "/photos/2020_02_13.jpg",
  "/photos/2020_03_08.jpg",
  "/photos/2020_04_07.jpg",
  "/photos/2020_04_24.jpg",
  "/photos/2022_01_25.jpg",
  "/photos/2022_06_30-2.jpg",
  "/photos/2022_09_05.jpg",
  "/photos/2022_09_20.jpg",
  "/photos/2022_09_21.jpg",
];

export const YEARS: number[] = [];
for (let y = 1999; y <= 2025; y++) YEARS.push(y);

// Deterministic pseudo-random helper
function prand(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
}

function seriesWithJump(seed: number, base: number, drift: number, jumpYear: number, jumpSize: number): number[] {
  const r = prand(seed);
  return YEARS.map((y, i) => {
    const noise = (r() - 0.5) * 0.02 * base;
    const jump = y >= jumpYear ? jumpSize : 0;
    return +(base + drift * i + noise + jump).toFixed(2);
  });
}

export const yearPoints: YearPoint[] = YEARS.map((year, i) => {
  // photo URL is REAL — picked deterministically from main folder.
  // anomaly / identity / note remain synthetic placeholders for now.
  const real = pickAnchor(year);
  const photo = real || PHOTO_POOL[i % PHOTO_POOL.length];
  // anomalies cluster around 2012 (suspected double swap) and later years
  let anomaly: Severity | undefined;
  if (year === 2012) anomaly = "warn";
  else if (year === 2014) anomaly = "danger";
  else if (year === 2015) anomaly = "ok";
  else if (year === 2017) anomaly = "ok";
  else if (year === 2022) anomaly = "warn";
  else if (year === 2023) anomaly = "danger";
  else if (year === 2025) anomaly = "warn";

  const identity: "A" | "B" = year >= 2015 && year <= 2020 ? "B" : "A";

  return {
    year,
    photo,
    anomaly,
    identity,
    note:
      year === 2012
        ? "Chronological inconsistency: sudden bone asymmetry shift"
        : year === 2014
        ? "High synthetic-material probability (silicone mask signature)"
        : undefined,
  };
});

// Metric 1 — bone asymmetry ratio (H0 support)
const skullRatio = seriesWithJump(11, 1.62, 0.006, 2012, 0.08).map((v) => +Math.min(1.8, v).toFixed(2));
// Metric 2 — neurocranium width (mm)
const neuroWidth = seriesWithJump(22, 131.2, 0.08, 2012, 1.4).map((v) => +v.toFixed(1));
// Metric 3 — orbital asymmetry angle (°)
const orbitalAngle = seriesWithJump(33, 2.1, 0.06, 2012, 0.9).map((v) => +v.toFixed(1));
// Metric 4 — facial BMI (tissue deficit index) — trends down with age
const facialBMI = YEARS.map((_, i) => {
  const r = prand(44 + i);
  return +(0.78 - i * 0.009 + (r() - 0.5) * 0.01).toFixed(2);
});
// Metric 5 — synthetic material probability (0..1) — bars
const synth = YEARS.map((y, i) => {
  const r = prand(55 + i);
  const base = 0.15 + r() * 0.2;
  const spike = y === 2012 || y === 2014 || y === 2023 ? 0.45 + r() * 0.2 : 0;
  return +Math.min(0.95, base + spike).toFixed(2);
});
// Metric 6 — texture complexity (LBP) — bars
const lbp = YEARS.map((y, i) => {
  const r = prand(66 + i);
  const base = 0.55 + r() * 0.25;
  const drop = y === 2012 || y === 2014 ? -0.25 : 0;
  return +Math.max(0.05, base + drop).toFixed(2);
});
// Metric 7 — estimated age (still synthetic; anchored to year offset)
const age = YEARS.map((_, i) => 46 + i);

// REAL metrics from the head-pose pipeline aggregates.
const realPhotoCount = realByYear(YEARS, (s) => s.count, 0);
const realMeanAbsYaw = realByYear(YEARS, (s) => s.meanAbsYaw, 0);
const realFrontalRatio = realByYear(YEARS, (s) => s.frontalRatio, 0);

// REAL face-crop luminance per year (from face_stats pipeline).
const REAL_LUM = yearLuminance(MAIN_PHOTOS);
const realMeanLum = YEARS.map((y) => REAL_LUM.find((s) => s.year === y)?.meanLum ?? 0);
const realStdLum = YEARS.map((y) => REAL_LUM.find((s) => s.year === y)?.stdLum ?? 0);

export const metrics: MetricConfig[] = [
  {
    id: "skull",
    title: "Bone asymmetry ratio",
    subtitle: "H0 · geometric",
    color: "#22c55e",
    kind: "line",
    domain: [1.55, 1.82],
    values: skullRatio,
    flags: YEARS.map((y) => (y === 2012 ? "warn" : undefined)),
  },
  {
    id: "neuro",
    title: "Neurocranium width",
    unit: "mm",
    subtitle: "frontal only",
    color: "#22c55e",
    kind: "line",
    domain: [130.5, 134.2],
    values: neuroWidth,
  },
  {
    id: "orbital",
    title: "Orbital asymmetry",
    unit: "°",
    subtitle: "pose-gated",
    color: "#22c55e",
    kind: "line",
    domain: [1.8, 4.2],
    values: orbitalAngle,
    flags: YEARS.map((y) => (y === 2012 ? "danger" : undefined)),
  },
  {
    id: "bmi",
    title: "Facial BMI",
    subtitle: "tissue deficit",
    color: "#38bdf8",
    kind: "line",
    domain: [0.45, 0.82],
    values: facialBMI,
  },
  {
    id: "synth",
    title: "Synthetic-material prob.",
    subtitle: "FFT + LBP + albedo",
    color: "#38bdf8",
    kind: "bar",
    domain: [0, 1],
    values: synth,
  },
  {
    id: "lbp",
    title: "Texture complexity (LBP)",
    color: "#a855f7",
    kind: "bar",
    domain: [0, 1],
    values: lbp,
  },
  {
    id: "age",
    title: "Estimated age",
    unit: "yr",
    color: "#a855f7",
    kind: "line",
    domain: [44, 68],
    values: age,
  },
  // === REAL metrics below this line ===
  {
    id: "real_count",
    title: "Photos / year (real)",
    subtitle: "from main folder",
    color: "#22c55e",
    kind: "bar",
    domain: [0, Math.max(1, ...realPhotoCount)],
    values: realPhotoCount,
  },
  {
    id: "real_yaw",
    title: "Mean |yaw| / year (real)",
    unit: "°",
    subtitle: "head-pose pipeline",
    color: "#38bdf8",
    kind: "line",
    domain: [0, Math.max(1, ...realMeanAbsYaw)],
    values: realMeanAbsYaw,
  },
  {
    id: "real_frontal",
    title: "Frontal ratio / year (real)",
    subtitle: "fraction classified frontal",
    color: "#a855f7",
    kind: "line",
    domain: [0, 1],
    values: realFrontalRatio,
  },
  {
    id: "real_lum",
    title: "Face mean luminance / year (real)",
    subtitle: "ITU-R BT.601, face crop",
    color: "#eab308",
    kind: "line",
    domain: [Math.max(0, Math.min(...realMeanLum.filter((x) => x > 0))) - 5, Math.max(...realMeanLum) + 5],
    values: realMeanLum,
  },
  {
    id: "real_lum_std",
    title: "Face luminance σ / year (real)",
    subtitle: "spread within year",
    color: "#eab308",
    kind: "bar",
    domain: [0, Math.max(...realStdLum) || 1],
    values: realStdLum,
  },
];

export const identitySegments: IdentitySegment[] = [
  { id: "A", from: 1999, to: 2014 },
  { id: "B", from: 2015, to: 2020 },
  { id: "A", from: 2021, to: 2025 },
];

export const eventMarkers: EventMarker[] = [
  { year: 2001, kind: "ok", title: "Baseline reconstruction" },
  { year: 2003, kind: "ok", title: "Calibration bucket good" },
  { year: 2005, kind: "warn", title: "Lighting variance elevated" },
  { year: 2006, kind: "ok", title: "Pose coverage complete" },
  { year: 2008, kind: "info", title: "New reference photo added" },
  { year: 2009, kind: "health", title: "Calibration health check" },
  { year: 2010, kind: "warn", title: "Minor tissue anomaly" },
  { year: 2011, kind: "info", title: "3DDFA_v3 re-run" },
  { year: 2012, kind: "danger", title: "Suspected identity swap" },
  { year: 2014, kind: "danger", title: "High silicone probability" },
  { year: 2015, kind: "calendar", title: "Cluster boundary" },
  { year: 2018, kind: "calendar", title: "Bayesian re-evaluation" },
  { year: 2020, kind: "calendar", title: "Cluster boundary" },
  { year: 2022, kind: "warn", title: "Chronological skip" },
  { year: 2023, kind: "danger", title: "Silicone spike" },
  { year: 2025, kind: "warn", title: "Open anomaly" },
];

// Volume histogram for bottom scrubber (photos per year, with bumps)
export const photoVolume: number[] = YEARS.map((y, i) => {
  const r = prand(777 + i);
  const base = 20 + Math.round(r() * 40);
  const bump = y >= 2008 && y <= 2015 ? 40 : 0;
  const bump2 = y >= 2019 && y <= 2022 ? 30 : 0;
  return base + bump + bump2;
});
