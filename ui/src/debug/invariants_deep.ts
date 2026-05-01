/**
 * Deeper cross-field invariants. These catch regressions that the basic
 * suite (invariants.ts) cannot, by comparing values that should agree across
 * different parts of the pipeline.
 */

import { PHOTOS } from "../mock/photos";
import { buildPhotoDetail } from "../mock/photoDetail";
import { GROUND_TRUTH } from "./ground_truth_accessor";
import type { Finding, InvariantContext } from "./invariants";

/* ---------------------------------------------------------------------- */
/* Coverage & integrity                                                   */
/* ---------------------------------------------------------------------- */

export async function checkPhotoYearCoverage(): Promise<Finding[]> {
  const out: Finding[] = [];
  const yearsWithPhotos = new Set(PHOTOS.map((p) => p.year));
  for (let y = 1999; y <= 2025; y++) {
    if (!yearsWithPhotos.has(y)) {
      out.push({
        id: `coverage.year_missing.${y}`,
        area: "consistency",
        severity: "warn",
        message: `No PhotoRecord exists for year ${y}`,
        hint: "Mock generator should produce at least one photo per year in 1999..2025",
      });
    }
  }
  // Total volume sanity (TZ says ~1700 photos)
  if (PHOTOS.length < 1500 || PHOTOS.length > 2200) {
    out.push({
      id: "coverage.total_volume",
      area: "consistency",
      severity: "info",
      message: "Total photo count is outside the expected 1500..2200 envelope",
      expected: "1500..2200",
      actual: PHOTOS.length,
    });
  }
  return out;
}

export async function checkAnomalyIntegrity(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const anomalies = await ctx.api.listAnomalies();
  const photoIds = new Set(PHOTOS.map((p) => p.id));
  for (const a of anomalies) {
    if (a.photoId && !photoIds.has(a.photoId)) {
      out.push({
        id: `anomaly.dangling_photoId.${a.id}`,
        area: "consistency",
        severity: "danger",
        message: `Anomaly references a non-existent photo id`,
        actual: a.photoId,
        hint: "Either fix the anomaly's photoId or remove the anomaly entirely",
      });
    }
    // year=0 = "no date in filename" (e.g. myface portraits, sha_dup
    // anomalies whose files are dateless). 2026 is the current year.
    if (a.year !== 0 && (a.year < 1999 || a.year > 2026)) {
      out.push({
        id: `anomaly.year_range.${a.id}`,
        area: "consistency",
        severity: "warn",
        message: `Anomaly year out of investigation window`,
        actual: a.year,
      });
    }
  }
  return out;
}

export async function checkCalibrationCoverage(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const cal = await ctx.api.getCalibration();
  const expectedPoses = ["frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right"];
  const expectedLights = ["daylight", "studio", "low_light", "mixed", "flash"];
  for (const p of expectedPoses) {
    for (const l of expectedLights) {
      const has = cal.buckets.some((b) => b.pose === p && b.light === l);
      if (!has) {
        out.push({
          id: `calibration.missing_bucket.${p}.${l}`,
          area: "calibration",
          severity: "warn",
          message: `Missing calibration bucket for pose=${p} light=${l}`,
          hint: "Calibration matrix should be a full pose × light cross-product",
        });
      }
    }
  }
  return out;
}

export async function checkInvestigationsIntegrity(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const inv = await ctx.api.listInvestigations();
  const ids = new Set<string>();
  for (const i of inv) {
    if (ids.has(i.id)) {
      out.push({
        id: `cases.duplicate.${i.id}`,
        area: "consistency",
        severity: "warn",
        message: "Duplicate case id",
        actual: i.id,
      });
    }
    ids.add(i.id);
    if (i.photoCount < 0 || i.photoCount > PHOTOS.length) {
      out.push({
        id: `cases.photo_count.${i.id}`,
        area: "consistency",
        severity: "info",
        message: `Case photoCount looks odd`,
        expected: `0..${PHOTOS.length}`,
        actual: i.photoCount,
      });
    }
  }
  return out;
}

export async function checkApiCatalog(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const cat = await ctx.api.getApiCatalog();
  const seen = new Set<string>();
  for (const e of cat) {
    const key = `${e.method} ${e.path}`;
    if (seen.has(key)) {
      out.push({
        id: `api_catalog.duplicate.${key}`,
        area: "consistency",
        severity: "warn",
        message: "Duplicate API catalog entry",
        actual: key,
      });
    }
    seen.add(key);
    if (!e.path.startsWith("/api/")) {
      out.push({
        id: `api_catalog.path.${key}`,
        area: "consistency",
        severity: "info",
        message: "API path should be /api/-prefixed",
        actual: e.path,
      });
    }
    if (!e.description || e.description.length < 10) {
      out.push({
        id: `api_catalog.thin_description.${key}`,
        area: "consistency",
        severity: "info",
        message: "API endpoint missing a meaningful description",
        actual: e.description ?? "",
      });
    }
  }
  return out;
}

/* ---------------------------------------------------------------------- */
/* Cross-component agreement                                              */
/* ---------------------------------------------------------------------- */

export async function checkTimelineVsPhotoDetail(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const t = await ctx.api.getTimeline();
  // The "estimated age" timeline metric should track 46 + i exactly (mock contract).
  const ageMetric = t.metrics.find((m) => m.id === "age");
  if (ageMetric) {
    for (let i = 0; i < ageMetric.values.length; i++) {
      const expected = 46 + i;
      if (ageMetric.values[i] !== expected) {
        out.push({
          id: `timeline.age_metric.${t.years[i]}`,
          area: "consistency",
          severity: "info",
          message: `age metric for year ${t.years[i]} drifted from 46 + i contract`,
          expected: String(expected),
          actual: ageMetric.values[i],
        });
        break; // one report is enough
      }
    }
  } else {
    out.push({
      id: "timeline.age_metric_missing",
      area: "consistency",
      severity: "warn",
      message: "Timeline missing 'age' metric row",
    });
  }

  // Per-year detail.bayes verdict should agree with year-point identity:
  // identity B at year y ⇒ detail.bayes.H1 should not be the smallest hypothesis.
  for (const yp of t.yearPoints) {
    if (yp.identity !== "B") continue;
    const d = buildPhotoDetail(yp.year, yp.photo || "");
    const probs = [d.bayes.H0, d.bayes.H1, d.bayes.H2];
    const minIdx = probs.indexOf(Math.min(...probs));
    if (minIdx === 1) {
      out.push({
        id: `consistency.cluster_b_h1_low.${yp.year}`,
        area: "bayes",
        severity: "warn",
        message: `Year ${yp.year} is in cluster B but H1 is the lowest posterior`,
        actual: probs,
        hint: "Cluster B implies suspected substitution; H1 should not be the smallest hypothesis",
      });
    }
  }
  return out;
}

export async function checkAgeingVsTimeline(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const [series, t] = await Promise.all([ctx.api.getAgeingSeries(), ctx.api.getTimeline()]);
  if (series.length !== t.years.length) {
    out.push({
      id: "ageing.length_mismatch",
      area: "ageing",
      severity: "danger",
      message: "Ageing series length does not match timeline years",
      expected: String(t.years.length),
      actual: series.length,
    });
  }
  // years must align position-wise
  for (let i = 0; i < Math.min(series.length, t.years.length); i++) {
    if (series[i].year !== t.years[i]) {
      out.push({
        id: `ageing.year_misalignment.${i}`,
        area: "ageing",
        severity: "danger",
        message: `Ageing series year[${i}] does not match timeline year[${i}]`,
        expected: String(t.years[i]),
        actual: series[i].year,
      });
      break;
    }
  }
  return out;
}

export async function checkExpandedDeterminism(): Promise<Finding[]> {
  const out: Finding[] = [];
  const sampleYears = [1999, 2005, 2012, 2017, 2025];
  for (const y of sampleYears) {
    const p = PHOTOS.find((x) => x.year === y);
    if (!p) continue;
    const d1 = buildPhotoDetail(y, p.photo);
    const d2 = buildPhotoDetail(y, p.photo);
    const a = JSON.stringify({
      zones: d1.zones,
      pose: d1.pose,
      expression: d1.expression,
      texture: d1.texture,
      bayes: d1.bayes,
      chronology: d1.chronology,
    });
    const b = JSON.stringify({
      zones: d2.zones,
      pose: d2.pose,
      expression: d2.expression,
      texture: d2.texture,
      bayes: d2.bayes,
      chronology: d2.chronology,
    });
    if (a !== b) {
      out.push({
        id: `determinism.year.${y}`,
        area: "consistency",
        severity: "warn",
        message: `buildPhotoDetail is non-deterministic for year ${y}`,
        hint: "Use a seeded RNG for every random source so audits are reproducible",
      });
    }
  }
  return out;
}

export async function checkLogsForErrors(): Promise<Finding[]> {
  const out: Finding[] = [];
  // Only meaningful in browser; in Node logger has no entries yet.
  if (typeof window === "undefined") return out;
  const buf: any[] = (window as any).deeputin?.logs ?? [];
  const errors = buf.filter((e) => e.level === "error");
  if (errors.length > 0) {
    out.push({
      id: "logs.error_count",
      area: "api",
      severity: "warn",
      message: `${errors.length} error-level entries in the live log buffer`,
      actual: errors.slice(-3).map((e) => `${e.scope}: ${e.message}`),
      hint: "Open Logs page filtered by level=error to inspect",
    });
  }
  return out;
}

export async function checkGroundTruthFiles(): Promise<Finding[]> {
  const out: Finding[] = [];
  const fileNames = new Set(GROUND_TRUTH.map((g) => g.file));
  if (fileNames.size !== GROUND_TRUTH.length) {
    out.push({
      id: "ground_truth.duplicate_file",
      area: "consistency",
      severity: "warn",
      message: "GROUND_TRUTH contains duplicate filenames",
    });
  }
  // The YYYY_MM_DD filename check applied to the old testphoto set; myface
  // photos are user-supplied with arbitrary names and have no such convention.
  return out;
}

import { checkSignals } from "./invariants_signals";
import { getDhashIndex } from "./dhashIndex";

export async function checkSimilarPhotos(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const seed = PHOTOS[200]?.id ?? PHOTOS[0]?.id;
  if (!seed) return out;
  const list = await ctx.api.similarPhotos(seed, 16);
  if (list.length === 0) {
    out.push({
      id: "similar.empty",
      area: "consistency",
      severity: "warn",
      message: "similarPhotos returned an empty list for a known seed",
      actual: seed,
    });
    return out;
  }
  if (list.some((p) => p.id === seed)) {
    out.push({
      id: "similar.includes_self",
      area: "consistency",
      severity: "warn",
      message: "similarPhotos result contains the seed photo",
      hint: "Filter by id !== seed in similarPhotos",
    });
  }
  if (new Set(list.map((p) => p.id)).size !== list.length) {
    out.push({
      id: "similar.duplicate_results",
      area: "consistency",
      severity: "warn",
      message: "similarPhotos returned duplicate ids",
    });
  }
  // dHash anchoring: at least 5% of returned photos should share a URL with
  // a hashed file (i.e. perceptual signal is actually being applied).
  const idx = await getDhashIndex();
  if (idx.size > 0) {
    const anchored = list.filter((p) => idx.has(p.photo));
    const anchoredFraction = anchored.length / list.length;
    if (anchoredFraction < 0.05) {
      out.push({
        id: "similar.no_dhash_anchor",
        area: "consistency",
        severity: "info",
        message: "similarPhotos result barely uses real dHash anchoring",
        actual: { anchored: anchored.length, total: list.length },
        hint: "Confirm the seed photo URL is in signal-report.json",
      });
    }
  }
  return out;
}

export const DEEP_INVARIANTS = [
  { id: "photo_year_coverage",         run: (_c: InvariantContext) => checkPhotoYearCoverage() },
  { id: "anomaly_integrity",           run: checkAnomalyIntegrity },
  { id: "calibration_coverage",        run: checkCalibrationCoverage },
  { id: "investigations_integrity",    run: checkInvestigationsIntegrity },
  { id: "api_catalog",                 run: checkApiCatalog },
  { id: "timeline_vs_photo_detail",    run: checkTimelineVsPhotoDetail },
  { id: "ageing_vs_timeline",          run: checkAgeingVsTimeline },
  { id: "expanded_determinism",        run: (_c: InvariantContext) => checkExpandedDeterminism() },
  { id: "logs_for_errors",             run: (_c: InvariantContext) => checkLogsForErrors() },
  { id: "ground_truth_files",          run: (_c: InvariantContext) => checkGroundTruthFiles() },
  { id: "signals",                     run: checkSignals },
  { id: "similar_photos",              run: checkSimilarPhotos },
];
