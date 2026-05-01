/**
 * Per-endpoint response validators. Each validator returns a list of
 * Violations — empty = all good. Validators are deliberately verbose and
 * explicit so that every field we care about is covered, and so future
 * algorithmic changes make their expectations visible in diffs.
 */

import type {
  TimelineSummary,
  CalibrationSummary,
  Job,
  AnomalyRecord,
  PipelineStage,
  CacheSummary,
  AgeingPoint,
  EvidenceBreakdown,
  PhotoListResult,
} from "../api/types";
import type { PhotoDetail } from "../mock/photoDetail";
import type { PhotoRecord } from "../mock/photos";
import { EXPECT, checkRange, checkSum } from "./expectations";
import type { Violation } from "./logger";

export function validateTimeline(t: TimelineSummary): Violation[] {
  const v: Violation[] = [];
  if (t.years.length < 20) {
    v.push({ field: "years.length", expected: ">= 20", actual: t.years.length, severity: "warn" });
  }
  const minY = Math.min(...t.years);
  const maxY = Math.max(...t.years);
  if (minY !== EXPECT.misc.year_coverage.min) {
    v.push({ field: "years.min", expected: `== ${EXPECT.misc.year_coverage.min}`, actual: minY, severity: "warn" });
  }
  if (maxY !== EXPECT.misc.year_coverage.max) {
    v.push({ field: "years.max", expected: `== ${EXPECT.misc.year_coverage.max}`, actual: maxY, severity: "warn" });
  }
  if (t.yearPoints.length !== t.years.length) {
    v.push({ field: "yearPoints.length", expected: `== years.length (${t.years.length})`, actual: t.yearPoints.length, severity: "danger" });
  }
  t.metrics.forEach((m) => {
    if (m.values.length !== t.years.length) {
      v.push({
        field: `metric[${m.id}].values.length`,
        expected: `== years.length (${t.years.length})`,
        actual: m.values.length,
        severity: "danger",
      });
    }
    // domain sanity by id — map timeline metric IDs to expectation keys
    const ranges: Record<string, keyof typeof EXPECT.metric> = {
      photo_count: "photo_count",
      mean_yaw: "mean_yaw",
      frontal_ratio: "frontal_ratio",
      age: "estimated_age",
    };
    const key = ranges[m.id];
    if (key) {
      m.values.forEach((val, i) => {
        const x = checkRange(`metric[${m.id}][${i}=${t.years[i]}]`, val, EXPECT.metric[key]);
        if (x) v.push(x);
      });
    }
  });
  const totalExpect = EXPECT.pipeline.total_photos_expected;
  const totalCheck = checkRange("totalPhotos", t.totalPhotos, totalExpect);
  if (totalCheck) v.push(totalCheck);
  return v;
}

export function validatePhotoList(r: PhotoListResult): Violation[] {
  const v: Violation[] = [];
  if (!Array.isArray(r.items)) {
    v.push({ field: "items", expected: "array", actual: typeof r.items, severity: "danger" });
  }
  r.items.forEach((p, i) => {
    if (!inYearRange(p.year)) {
      v.push({ field: `items[${i}].year`, expected: "1999..2025", actual: p.year, severity: "warn" });
    }
    const x = checkRange(`items[${i}].syntheticProb`, p.syntheticProb, EXPECT.metric.texture_silicone_prob);
    if (x) v.push(x);
    const y = checkRange(`items[${i}].bayesH0`, p.bayesH0, { min: 0, max: 1 });
    if (y) v.push(y);
  });
  return v;
}

export function validatePhoto(p: PhotoRecord): Violation[] {
  const v: Violation[] = [];
  if (!inYearRange(p.year)) {
    v.push({ field: "year", expected: "1999..2025", actual: p.year, severity: "warn" });
  }
  if (!p.id || !p.id.startsWith("main-")) {
    v.push({ field: "id", expected: "starts with 'main-'", actual: p.id, severity: "warn" });
  }
  return v;
}

export function validatePhotoDetail(d: PhotoDetail): Violation[] {
  const v: Violation[] = [];
  // Zone count can be less than 21 when expression exclusion removes jaw/cheek zones
  if (d.zones.length < 18 || d.zones.length > 21) {
    v.push({ field: "zones.length", expected: "18..21 (21 minus expression-excluded)", actual: d.zones.length, severity: "warn" });
  }
  d.zones.forEach((z, i) => {
    const w = checkRange(`zones[${i}=${z.id}].weight`, z.weight, EXPECT.zone.weight);
    if (w) v.push(w);
    const s = checkRange(`zones[${i}=${z.id}].score`, z.score, EXPECT.zone.score);
    if (s) v.push(s);
  });
  ["yaw", "pitch", "roll"].forEach((k) => {
    const r =
      k === "yaw" ? EXPECT.pose.yaw_deg : k === "pitch" ? EXPECT.pose.pitch_deg : EXPECT.pose.roll_deg;
    const x = checkRange(`pose.${k}`, (d.pose as any)[k], r);
    if (x) v.push(x);
  });
  const c = checkRange("pose.confidence", d.pose.confidence, EXPECT.pose.confidence, "info");
  if (c) v.push(c);

  const s = checkRange("expression.smile", d.expression.smile, EXPECT.expression.smile);
  if (s) v.push(s);
  const j = checkRange("expression.jawOpen", d.expression.jawOpen, EXPECT.expression.jaw_open);
  if (j) v.push(j);

  const syn = checkRange("texture.syntheticProb", d.texture.syntheticProb, EXPECT.metric.texture_silicone_prob);
  if (syn) v.push(syn);

  const sum = checkSum(
    "bayes.sum(H0+H1+H2)",
    [d.bayes.H0, d.bayes.H1, d.bayes.H2],
    EXPECT.bayes.posterior_sum_min,
    EXPECT.bayes.posterior_sum_max
  );
  if (sum) v.push(sum);

  return v;
}

export function validateEvidence(e: EvidenceBreakdown): Violation[] {
  const v: Violation[] = [];

  const ps = checkSum(
    "priors.sum",
    [e.priors.H0, e.priors.H1, e.priors.H2],
    EXPECT.bayes.prior_sum_min,
    EXPECT.bayes.prior_sum_max
  );
  if (ps) v.push(ps);

  const pos = checkSum(
    "posteriors.sum",
    [e.posteriors.H0, e.posteriors.H1, e.posteriors.H2],
    EXPECT.bayes.posterior_sum_min,
    EXPECT.bayes.posterior_sum_max
  );
  if (pos) v.push(pos);

  if (e.posteriors.H1 > EXPECT.bayes.H1_suspicion_threshold && e.verdict !== "H1") {
    v.push({
      field: "verdict",
      expected: `H1 when P(H1) > ${EXPECT.bayes.H1_suspicion_threshold}`,
      actual: `${e.verdict} with P(H1)=${e.posteriors.H1}`,
      severity: "warn",
      note: "High H1 posterior but verdict not H1 — inspect evidence weighting.",
    });
  }

  if (e.chronology.deltaYears < 0) {
    v.push({ field: "chronology.deltaYears", expected: ">= 0", actual: e.chronology.deltaYears, severity: "danger" });
  }

  const syn = checkRange("texture.syntheticProb", e.texture.syntheticProb, EXPECT.metric.texture_silicone_prob);
  if (syn) v.push(syn);

  if (e.pose.mutualVisibility > 21) {
    v.push({
      field: "pose.mutualVisibility",
      expected: "<= 21",
      actual: e.pose.mutualVisibility,
      severity: "danger",
    });
  }
  return v;
}

export function validateCalibration(c: CalibrationSummary): Violation[] {
  const v: Violation[] = [];
  const levels = c.buckets.reduce<Record<string, number>>((a, b) => {
    a[b.level] = (a[b.level] ?? 0) + 1;
    return a;
  }, {});
  if ((levels["unreliable"] ?? 0) > EXPECT.calibration.unreliable_buckets_max) {
    v.push({
      field: "calibration.unreliable_buckets",
      expected: `<= ${EXPECT.calibration.unreliable_buckets_max}`,
      actual: levels["unreliable"] ?? 0,
      severity: "warn",
    });
  }
  if ((levels["high"] ?? 0) < EXPECT.calibration.high_buckets_min) {
    v.push({
      field: "calibration.high_buckets",
      expected: `>= ${EXPECT.calibration.high_buckets_min}`,
      actual: levels["high"] ?? 0,
      severity: "warn",
    });
  }
  c.buckets.forEach((b, i) => {
    if (b.count < 0) {
      v.push({ field: `buckets[${i}].count`, expected: ">= 0", actual: b.count, severity: "danger" });
    }
  });
  return v;
}

export function validateJobs(jobs: Job[]): Violation[] {
  const v: Violation[] = [];
  jobs.forEach((j, i) => {
    if (j.progress < 0 || j.progress > 1) {
      v.push({ field: `jobs[${i}=${j.id}].progress`, expected: "0..1", actual: j.progress, severity: "warn" });
    }
    if (j.status === "done" && j.progress !== 1) {
      v.push({
        field: `jobs[${i}=${j.id}]`,
        expected: "status=done implies progress=1",
        actual: `progress=${j.progress}`,
        severity: "warn",
      });
    }
  });
  return v;
}

export function validateAnomalies(a: AnomalyRecord[]): Violation[] {
  const v: Violation[] = [];
  a.forEach((x, i) => {
    if (!inYearRange(x.year)) {
      v.push({ field: `anomalies[${i}].year`, expected: "1999..2025", actual: x.year, severity: "warn" });
    }
  });
  return v;
}

export function validatePipeline(stages: PipelineStage[]): Violation[] {
  const v: Violation[] = [];
  stages.forEach((s, i) => {
    if (s.outputCount > s.inputCount) {
      v.push({
        field: `stages[${i}=${s.id}]`,
        expected: "outputCount <= inputCount",
        actual: `in=${s.inputCount} out=${s.outputCount}`,
        severity: "danger",
      });
    }
    const dropPct = i === 0 ? 0 : ((stages[i - 1].outputCount - s.outputCount) / (stages[i - 1].outputCount || 1)) * 100;
    if (dropPct > EXPECT.pipeline.stage_drop_pct_max) {
      v.push({
        field: `stages[${i}=${s.id}].drop`,
        expected: `<= ${EXPECT.pipeline.stage_drop_pct_max}%`,
        actual: `${dropPct.toFixed(1)}%`,
        severity: "warn",
      });
    }
    if (s.avgMs > EXPECT.pipeline.avg_ms_warn_threshold) {
      v.push({
        field: `stages[${i}=${s.id}].avgMs`,
        expected: `<= ${EXPECT.pipeline.avg_ms_warn_threshold}ms`,
        actual: s.avgMs,
        severity: "info",
      });
    }
    if (s.gpuMemoryMB && s.gpuMemoryMB > EXPECT.pipeline.gpu_mb_budget) {
      v.push({
        field: `stages[${i}=${s.id}].gpu`,
        expected: `<= ${EXPECT.pipeline.gpu_mb_budget}MB`,
        actual: s.gpuMemoryMB,
        severity: "danger",
      });
    }
  });
  return v;
}

export function validateCache(c: CacheSummary): Violation[] {
  const v: Violation[] = [];
  if (c.currentSize > c.maxSize) {
    v.push({
      field: "cache.currentSize",
      expected: `<= maxSize (${c.maxSize})`,
      actual: c.currentSize,
      severity: "danger",
    });
  }
  if (c.vramFootprintMB > c.vramBudgetMB) {
    v.push({
      field: "cache.vramFootprintMB",
      expected: `<= budget ${c.vramBudgetMB}`,
      actual: c.vramFootprintMB,
      severity: "danger",
    });
  }
  if (c.vramFootprintMB / c.vramBudgetMB > EXPECT.cache.vram_warn_ratio) {
    v.push({
      field: "cache.vram_utilization",
      expected: `<= ${EXPECT.cache.vram_warn_ratio * 100}%`,
      actual: `${((c.vramFootprintMB / c.vramBudgetMB) * 100).toFixed(1)}%`,
      severity: "warn",
    });
  }
  return v;
}

export function validateAgeing(series: AgeingPoint[]): Violation[] {
  const v: Violation[] = [];
  const outliers = series.filter((p) => p.outlier);
  if (outliers.length > EXPECT.ageing.outlier_count.max) {
    v.push({
      field: "ageing.outlier_count",
      expected: `<= ${EXPECT.ageing.outlier_count.max}`,
      actual: outliers.length,
      severity: "warn",
      note: "Unexpectedly many outliers — inspect ageing model residuals.",
    });
  }
  series.forEach((p, i) => {
    if (!inYearRange(p.year)) {
      v.push({ field: `ageing[${i}].year`, expected: "1999..2025", actual: p.year, severity: "warn" });
    }
  });
  return v;
}

function inYearRange(y: number): boolean {
  return y >= EXPECT.misc.year_coverage.min && y <= EXPECT.misc.year_coverage.max;
}
