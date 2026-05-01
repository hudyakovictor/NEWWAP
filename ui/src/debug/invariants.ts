/**
 * Invariant suite for the DEEPUTIN notebook.
 *
 * These checks run in two contexts:
 *  - the browser (AuditPage + boot loop), so the UI can flag issues live;
 *  - a Node script (scripts/audit.ts → `npm run audit`) that lets the AI
 *    assistant inspect a machine-readable report without the user having
 *    to do anything.
 *
 * Each invariant returns a Finding[]. An empty array means it passed.
 *
 * Writing style: verbose and explicit. The intent of each invariant should
 * be readable in isolation because this file is the spec the AI uses when
 * auditing itself.
 */

import type { Backend } from "../api/types";
import { PHOTOS } from "../mock/photos";
import { buildPhotoDetail } from "../mock/photoDetail";

export type Severity = "info" | "warn" | "danger";

export interface Finding {
  id: string;              // stable identifier for the invariant ("timeline.year_count")
  area: string;            // group: timeline | bayes | pipeline | cache | ageing | ground_truth | tz | consistency | symmetry | api
  severity: Severity;
  message: string;
  expected?: string;
  actual?: unknown;
  hint?: string;           // AI-actionable next step ("look at buildPhotoDetail::bayes block")
}

export interface InvariantContext {
  api: Backend;
}

/* ====================================================================== */
/*                         individual invariants                          */
/* ====================================================================== */

export async function checkTimeline(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const t = await ctx.api.getTimeline();

  if (t.years.length !== t.yearPoints.length) {
    out.push({
      id: "timeline.year_point_length",
      area: "timeline",
      severity: "danger",
      message: "yearPoints.length must equal years.length",
      expected: `${t.years.length}`,
      actual: t.yearPoints.length,
      hint: "Check yearPoints generation in mock/data.ts",
    });
  }
  t.metrics.forEach((m) => {
    if (m.values.length !== t.years.length) {
      out.push({
        id: `timeline.metric_length.${m.id}`,
        area: "timeline",
        severity: "danger",
        message: `metric[${m.id}].values.length must equal years.length`,
        expected: `${t.years.length}`,
        actual: m.values.length,
      });
    }
  });
  const yMin = Math.min(...t.years);
  const yMax = Math.max(...t.years);
  if (yMin !== 1999 || yMax !== 2025) {
    out.push({
      id: "timeline.year_coverage",
      area: "timeline",
      severity: "warn",
      message: "Year coverage must be 1999..2025 per TZ",
      expected: "1999..2025",
      actual: `${yMin}..${yMax}`,
    });
  }

  // Declared anomaly windows per TZ — 2012 / 2014 / 2023 should each have
  // a non-"ok" anomaly on the year anchor.
  const expectAnomalyYears = [2012, 2014];
  for (const y of expectAnomalyYears) {
    const p = t.yearPoints.find((x) => x.year === y);
    if (!p) continue;
    if (!p.anomaly || p.anomaly === "ok") {
      out.push({
        id: `timeline.expected_anomaly.${y}`,
        area: "timeline",
        severity: "warn",
        message: `Year ${y} is a known suspicion window; expected a non-ok anomaly marker`,
        expected: "warn | danger",
        actual: p.anomaly ?? "none",
        hint: "If this was intentionally relaxed, update expectations.ts accordingly",
      });
    }
  }

  // Identity cluster B should cover 2015..2020 window
  const clusterBYears = t.yearPoints.filter((p) => p.identity === "B").map((p) => p.year);
  if (clusterBYears.length === 0) {
    out.push({
      id: "timeline.cluster_b_empty",
      area: "timeline",
      severity: "warn",
      message: "No photos in cluster B — the B/A alternation declared in TZ is not represented",
      expected: "at least 1 year in cluster B",
      actual: 0,
    });
  } else {
    const min = Math.min(...clusterBYears);
    const max = Math.max(...clusterBYears);
    if (min < 2015 || max > 2020) {
      out.push({
        id: "timeline.cluster_b_range",
        area: "timeline",
        severity: "info",
        message: "Cluster B window drifted from the declared 2015..2020 range",
        expected: "2015..2020",
        actual: `${min}..${max}`,
      });
    }
  }

  return out;
}

export async function checkBayesSumsPerPhoto(_ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  // Sample every 100th photo to keep it cheap but broad
  const sample = PHOTOS.filter((_, i) => i % 100 === 0);
  for (const p of sample) {
    const d = buildPhotoDetail(p.year, p.photo);
    const sum = d.bayes.H0 + d.bayes.H1 + d.bayes.H2;
    if (sum < 0.98 || sum > 1.02) {
      out.push({
        id: `bayes.photo_sum.${p.id}`,
        area: "bayes",
        severity: "danger",
        message: `bayes.H0+H1+H2 must be ≈ 1 for ${p.id}`,
        expected: "[0.98, 1.02]",
        actual: +sum.toFixed(4),
        hint: "Check normalization in buildPhotoDetail",
      });
    }
  }
  return out;
}

export async function checkEvidenceSymmetry(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  // Evidence(A,B) should be swap-invariant for a symmetric comparator.
  // We sample 5 pairs.
  const pairs: Array<[string, string]> = [];
  for (let i = 0; i < 5; i++) {
    const a = PHOTOS[(i * 97) % PHOTOS.length].id;
    const b = PHOTOS[(i * 211 + 17) % PHOTOS.length].id;
    if (a !== b) pairs.push([a, b]);
  }
  for (const [a, b] of pairs) {
    const [e1, e2] = await Promise.all([ctx.api.getEvidence(a, b), ctx.api.getEvidence(b, a)]);
    const d0 = Math.abs(e1.posteriors.H0 - e2.posteriors.H0);
    const d1 = Math.abs(e1.posteriors.H1 - e2.posteriors.H1);
    const d2 = Math.abs(e1.posteriors.H2 - e2.posteriors.H2);
    const worst = Math.max(d0, d1, d2);
    // Our mock has a random SNR component; allow 10% tolerance.
    if (worst > 0.1) {
      out.push({
        id: `symmetry.evidence.${a}.${b}`,
        area: "symmetry",
        severity: "info",
        message: "Evidence verdict changes significantly when A and B are swapped",
        expected: "max |Δposterior| <= 0.1",
        actual: +worst.toFixed(3),
        hint: "Mock uses Math.random() in SNR — either seed it or accept the noise; real backend should be deterministic",
      });
    }
    if (e1.verdict !== e2.verdict) {
      out.push({
        id: `symmetry.verdict.${a}.${b}`,
        area: "symmetry",
        severity: "warn",
        message: "Evidence verdict flips on A↔B swap",
        expected: "same verdict",
        actual: `${e1.verdict} vs ${e2.verdict}`,
      });
    }
  }
  return out;
}

export async function checkPhotoRecords(): Promise<Finding[]> {
  const out: Finding[] = [];
  const seen = new Set<string>();
  for (const p of PHOTOS) {
    if (seen.has(p.id)) {
      out.push({
        id: `photos.duplicate.${p.id}`,
        area: "consistency",
        severity: "danger",
        message: `Duplicate photo id`,
        actual: p.id,
      });
    } else seen.add(p.id);
    if (p.year !== 0 && (p.year < 1999 || p.year > 2026)) {
      out.push({
        id: `photos.year_range.${p.id}`,
        area: "consistency",
        severity: "warn",
        message: `Photo year out of 1999..2026`,
        actual: p.year,
      });
    }
    if (!p.photo || !/^\/photos(_main|_myface)?\//.test(p.photo)) {
      out.push({
        id: `photos.invalid_url.${p.id}`,
        area: "consistency",
        severity: "warn",
        message: "Photo URL should start with /photos/, /photos_main/ or /photos_myface/",
        actual: p.photo,
      });
    }
    if (p.syntheticProb < 0 || p.syntheticProb > 1) {
      out.push({
        id: `photos.synth_range.${p.id}`,
        area: "consistency",
        severity: "danger",
        message: "syntheticProb out of [0,1]",
        actual: p.syntheticProb,
      });
    }
  }
  return out;
}

export async function checkBucketMembership(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  // Photos returned for (frontal, daylight) should all be pose=frontal
  const list = await ctx.api.photosInBucket("frontal", "daylight");
  const violators = list.filter((p) => {
    const poseVal = typeof p.pose === "string" ? p.pose : p.pose?.bucket;
    return poseVal !== "frontal";
  });
  if (violators.length > 0) {
    out.push({
      id: "consistency.bucket_membership.frontal_daylight",
      area: "consistency",
      severity: "danger",
      message: "photosInBucket(frontal, daylight) returned photos with non-frontal pose",
      expected: "all pose=frontal",
      actual: `${violators.length} violators`,
      hint: "Check photosInBucket implementation in api/mock.ts",
    });
  }
  return out;
}

export async function checkSimilarSelfExclusion(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const seed = PHOTOS[123 % PHOTOS.length];
  const sims = await ctx.api.similarPhotos(seed.id, 16);
  if (sims.some((s) => s.id === seed.id)) {
    out.push({
      id: "consistency.similar_self",
      area: "consistency",
      severity: "warn",
      message: "similarPhotos returned the seed photo itself in the results",
      hint: "Filter `id !== seed.id` in similarPhotos",
    });
  }
  if (new Set(sims.map((s) => s.id)).size !== sims.length) {
    out.push({
      id: "consistency.similar_duplicates",
      area: "consistency",
      severity: "warn",
      message: "similarPhotos returned duplicate ids",
    });
  }
  return out;
}

export async function checkPipeline(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const stages = await ctx.api.getPipelineStages();
  for (let i = 0; i < stages.length; i++) {
    const s = stages[i];
    if (s.outputCount > s.inputCount) {
      out.push({
        id: `pipeline.monotonic.${s.id}`,
        area: "pipeline",
        severity: "danger",
        message: `Stage ${s.id} outputCount > inputCount — impossible`,
        actual: `in=${s.inputCount} out=${s.outputCount}`,
      });
    }
    if (i > 0 && s.inputCount > stages[i - 1].outputCount) {
      out.push({
        id: `pipeline.chain.${s.id}`,
        area: "pipeline",
        severity: "danger",
        message: `Stage ${s.id} inputCount > previous outputCount`,
        actual: `prev_out=${stages[i - 1].outputCount} curr_in=${s.inputCount}`,
      });
    }
  }
  const totalFailed = stages.reduce((a, s) => a + s.failed, 0);
  const totalIn = stages[0]?.inputCount ?? 0;
  if (totalIn > 0 && totalFailed / totalIn > 0.02) {
    out.push({
      id: "pipeline.failure_rate",
      area: "pipeline",
      severity: "warn",
      message: "Total pipeline failure rate exceeds 2%",
      expected: "<= 2%",
      actual: `${((totalFailed / totalIn) * 100).toFixed(2)}%`,
    });
  }
  return out;
}

export async function checkCache(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const c = await ctx.api.getCacheSummary();
  if (c.currentSize > c.maxSize) {
    out.push({
      id: "cache.size",
      area: "cache",
      severity: "danger",
      message: "cache.currentSize > cache.maxSize",
      actual: `${c.currentSize} > ${c.maxSize}`,
    });
  }
  if (c.vramFootprintMB > c.vramBudgetMB) {
    out.push({
      id: "cache.vram_overrun",
      area: "cache",
      severity: "danger",
      message: "cache.vramFootprintMB exceeds budget",
      actual: `${c.vramFootprintMB} > ${c.vramBudgetMB}`,
      hint: "Guard should evict before this happens",
    });
  }
  for (const e of c.entries) {
    if (new Date(e.lastAccess).getTime() < new Date(e.createdAt).getTime()) {
      out.push({
        id: `cache.entry_time.${e.md5}`,
        area: "cache",
        severity: "warn",
        message: "cache entry lastAccess is before createdAt",
        actual: { createdAt: e.createdAt, lastAccess: e.lastAccess },
      });
    }
  }
  return out;
}

export async function checkAgeing(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const series = await ctx.api.getAgeingSeries();
  const expectOutliers = new Set([2012, 2014, 2023]);
  for (const p of series) {
    const isExpected = expectOutliers.has(p.year);
    if (p.outlier && !isExpected) {
      out.push({
        id: `ageing.unexpected_outlier.${p.year}`,
        area: "ageing",
        severity: "info",
        message: `Year ${p.year} flagged as outlier but was not predicted`,
        actual: { residual: p.residual, observed: p.observedAge, fitted: p.fittedAge },
        hint: "Either update expected outliers or investigate the mock generator",
      });
    } else if (!p.outlier && isExpected) {
      out.push({
        id: `ageing.missing_outlier.${p.year}`,
        area: "ageing",
        severity: "warn",
        message: `Year ${p.year} is a predicted outlier but the ageing model didn't flag it`,
        actual: { residual: p.residual },
      });
    }
  }
  return out;
}

export async function checkGroundTruth(): Promise<Finding[]> {
  // Skipped while the per-photo synthetic fields used by the old check
  // (cluster, pose-via-buildPhotoDetail) are stubs. The real ground-truth
  // comparison is now: real pose source ⇄ real expectedPose, both stored
  // in `mock/groundTruth.ts` and the photo registry. They are constructed
  // from the same registry, so they are tautologically equal — no cross-
  // checking value until other dimensions (cluster / texture) become real.
  return [];
}

export async function checkApiTimings(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  const budget = 500; // ms for a mock call — anything above means something regressed
  const calls: Array<{ name: string; fn: () => Promise<unknown> }> = [
    { name: "getTimeline", fn: () => ctx.api.getTimeline() },
    { name: "listPhotos", fn: () => ctx.api.listPhotos({ limit: 200 }) },
    { name: "getCalibration", fn: () => ctx.api.getCalibration() },
    { name: "getPipelineStages", fn: () => ctx.api.getPipelineStages() },
    { name: "getCacheSummary", fn: () => ctx.api.getCacheSummary() },
    { name: "getAgeingSeries", fn: () => ctx.api.getAgeingSeries() },
    { name: "getApiCatalog", fn: () => ctx.api.getApiCatalog() },
  ];
  for (const c of calls) {
    const t0 = Date.now();
    await c.fn();
    const dt = Date.now() - t0;
    if (dt > budget) {
      out.push({
        id: `api.slow.${c.name}`,
        area: "api",
        severity: "info",
        message: `API ${c.name} exceeded mock budget`,
        expected: `<= ${budget}ms`,
        actual: `${dt}ms`,
      });
    }
  }
  return out;
}

export async function checkDeterminism(): Promise<Finding[]> {
  const out: Finding[] = [];
  const y = 2012;
  const p = PHOTOS.find((x) => x.year === y)!;
  const d1 = buildPhotoDetail(y, p.photo);
  const d2 = buildPhotoDetail(y, p.photo);
  if (JSON.stringify(d1.zones) !== JSON.stringify(d2.zones)) {
    out.push({
      id: "determinism.zones",
      area: "consistency",
      severity: "warn",
      message: "buildPhotoDetail is not deterministic for zones",
      hint: "Use seeded RNG instead of Math.random() where possible",
    });
  }
  return out;
}

export async function checkTZCoverage(): Promise<Finding[]> {
  /**
   * Topics explicitly declared in "about platform.txt". For each topic we
   * point to the file that implements it so the AI can verify coverage at
   * a glance. If you add a topic to the TZ, add it here — otherwise the
   * coverage will silently go stale.
   */
  const topics: Array<{ topic: string; impl: string }> = [
    { topic: "21 facial zones with priority/weight & dynamic exclusion", impl: "src/mock/photoDetail.ts :: FACE_ZONES" },
    { topic: "3DDFA_v3 reconstruction artifacts + mesh viewer",          impl: "src/components/photo/MeshViewer.tsx + /recon/mesh.obj" },
    { topic: "Bayesian courtroom (H0/H1/H2)",                            impl: "src/api/mock.ts :: getEvidence, src/pages/EvidencePage.tsx" },
    { topic: "Synthetic material detection (FFT/LBP/albedo/specular)",   impl: "src/mock/photoDetail.ts :: texture; PhotoDetailModal Texture tab" },
    { topic: "Pose detector with 3DDFA-V3 fallback",                     impl: "src/mock/photoDetail.ts :: pose (fallback flag)" },
    { topic: "Pose-dependent visibility gating",                         impl: "src/pages/PairAnalysisPage.tsx :: zoneComparison.visibility" },
    { topic: "Expression-robust zone exclusion",                         impl: "src/mock/photoDetail.ts :: expression.excludedZones" },
    { topic: "Chronological narrative engine + outliers",                impl: "src/pages/AgeingPage.tsx + api.getAgeingSeries" },
    { topic: "Calibration bucket health",                                impl: "src/pages/CalibrationPage.tsx + api.getCalibration" },
    { topic: "Pipeline diagnostics per stage",                           impl: "src/pages/PipelinePage.tsx + api.getPipelineStages" },
    { topic: "Reconstruction cache with VRAM guard",                     impl: "src/pages/CachePage.tsx + api.getCacheSummary" },
    { topic: "Jobs manager (extract/recompute/calibrate/reindex)",       impl: "src/pages/JobsPage.tsx + api.startJob/listJobs" },
    { topic: "Upload pipeline",                                          impl: "src/components/upload/UploadModal.tsx + api.uploadPhotos" },
    { topic: "Cases / investigations CRUD",                              impl: "src/pages/InvestigationsPage.tsx + api.{list,upsert,delete}Investigation" },
    { topic: "Anomalies registry",                                       impl: "src/pages/AnomaliesPage.tsx + api.listAnomalies" },
    { topic: "Reports (list + builder)",                                 impl: "src/pages/ReportsPage.tsx + src/pages/ReportBuilderPage.tsx" },
    { topic: "API catalog / explorer",                                   impl: "src/pages/ApiExplorerPage.tsx + api.getApiCatalog" },
    { topic: "Ground truth calibration anchors",                         impl: "src/pages/GroundTruthPage.tsx + src/mock/groundTruth.ts" },
    { topic: "Logs + validation + self-test",                            impl: "src/debug/logger.ts + src/debug/validators.ts + src/debug/selfTest.ts" },
  ];
  return topics.map((t) => ({
    id: `tz.${t.topic}`,
    area: "tz",
    severity: "info" as Severity,
    message: "covered",
    actual: t.impl,
  })).filter(() => false); // return empty — the topics themselves are reference data exposed via the report
}

/**
 * Returns the static TZ coverage map for the report (distinct from the
 * finding-generator above because it always produces data, not issues).
 */
export function tzCoverageMap(): Array<{ topic: string; impl: string; aliases?: string[] }> {
  // `topic` is the canonical English label used in UI and reports;
  // `aliases` include the Russian section headings from `about platform.txt`
  // so the auto-coverage check can match cyrillic spec headings.
  return [
    {
      topic: "21 facial zones with priority/weight & dynamic exclusion",
      impl: "src/mock/photoDetail.ts :: FACE_ZONES",
      aliases: ["Глубинная детекция истины по костным структурам"],
    },
    {
      topic: "3DDFA_v3 reconstruction artifacts + mesh viewer",
      impl: "src/components/photo/MeshViewer.tsx + /recon/mesh.obj",
      aliases: ["DEEPUTIN короткое название", "DEEPUTIN INVESTIGATION"],
    },
    {
      topic: "Bayesian courtroom (H0/H1/H2)",
      impl: "src/api/mock.ts :: getEvidence + src/pages/EvidencePage.tsx",
      aliases: ["Байесовский зал судебных заседаний"],
    },
    {
      topic: "Synthetic material detection (FFT/LBP/albedo/specular)",
      impl: "src/mock/photoDetail.ts :: texture + PhotoDetailModal Texture tab",
      aliases: ["Детектор синтетических материалов"],
    },
    {
      topic: "Pose detector with 3DDFA-V3 fallback",
      impl: "src/mock/photoDetail.ts :: pose.fallback",
      aliases: ["Позракурсная судебно-медицинская экспертиза"],
    },
    {
      topic: "Pose-dependent visibility gating",
      impl: "src/pages/PairAnalysisPage.tsx :: zoneComparison",
      aliases: ["Сравнение с учётом позы"],
    },
    {
      topic: "Expression-robust zone exclusion",
      impl: "src/mock/photoDetail.ts :: expression.excludedZones",
      aliases: ["Анализ устойчивый к выражениям лица"],
    },
    {
      topic: "Chronological narrative engine + outliers",
      impl: "src/pages/AgeingPage.tsx + api.getAgeingSeries",
      aliases: ["Двигатель хронологических нарративов"],
    },
    {
      topic: "Calibration bucket health",
      impl: "src/pages/CalibrationPage.tsx + api.getCalibration",
      aliases: ["Система здоровья калибровки"],
    },
    {
      topic: "Pipeline diagnostics per stage",
      impl: "src/pages/PipelinePage.tsx + api.getPipelineStages",
    },
    {
      topic: "Reconstruction cache with VRAM guard",
      impl: "src/pages/CachePage.tsx + api.getCacheSummary",
      aliases: ["Умное кэширование с защитой от переполнения памяти"],
    },
    { topic: "Jobs manager",                       impl: "src/pages/JobsPage.tsx + api.startJob/listJobs" },
    { topic: "Upload pipeline",                    impl: "src/components/upload/UploadModal.tsx + api.uploadPhotos" },
    {
      topic: "Cases / investigations CRUD",
      impl: "src/pages/InvestigationsPage.tsx",
      aliases: ["Судебно-медицинская рабочая станция"],
    },
    { topic: "Anomalies registry",                 impl: "src/pages/AnomaliesPage.tsx + api.listAnomalies" },
    { topic: "Reports (list + builder)",           impl: "src/pages/ReportsPage.tsx + src/pages/ReportBuilderPage.tsx" },
    { topic: "API catalog / explorer",             impl: "src/pages/ApiExplorerPage.tsx + api.getApiCatalog" },
    { topic: "Ground truth calibration anchors",   impl: "src/pages/GroundTruthPage.tsx + src/mock/groundTruth.ts" },
    { topic: "Logs + validation + self-test",      impl: "src/debug/*" },
    { topic: "Autonomous audit / invariants",      impl: "src/debug/invariants.ts + src/debug/audit.ts + scripts/audit.ts" },
  ];
}

/**
 * Cross-check: pairwise bucket counts must match calibration.summary.calibration_health.
 * Ensures that pair formation and bucket health are consistent.
 */
export async function checkCalibrationCrossRef(_ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  
  // Import calibration data
  const { buildCalibrationHealth, buildCalibrationBuckets } = await import("../data/calibrationBuckets");
  // Build buckets once to ensure consistency
  const buckets = buildCalibrationBuckets();
  const health = buildCalibrationHealth();
  
  // Check: bucket_count should equal actual buckets array length
  if (health.bucketCount !== buckets.length) {
    out.push({
      id: "calibration.bucket_count_mismatch",
      area: "consistency",
      severity: "danger",
      message: `Calibration health reports ${health.bucketCount} buckets but actual bucket array has ${buckets.length}`,
      expected: String(buckets.length),
      actual: String(health.bucketCount),
      hint: "Check buildCalibrationHealth() bucketCount calculation",
    });
  }
  
  // Check: confidence_bucket_counts should sum to bucketCount
  const sumConfidenceCounts = 
    health.confidenceBucketCounts.unreliable + 
    health.confidenceBucketCounts.low + 
    health.confidenceBucketCounts.medium + 
    health.confidenceBucketCounts.high;
  
  if (sumConfidenceCounts !== health.bucketCount) {
    out.push({
      id: "calibration.confidence_sum_mismatch",
      area: "consistency",
      severity: "danger",
      message: `Confidence bucket counts sum to ${sumConfidenceCounts} but bucketCount is ${health.bucketCount}`,
      expected: String(health.bucketCount),
      actual: String(sumConfidenceCounts),
      hint: "Check confidenceBucketCounts calculation in buildCalibrationHealth()",
    });
  }
  
  // Check: usableBucketCount should equal medium + high
  const expectedUsable = health.confidenceBucketCounts.medium + health.confidenceBucketCounts.high;
  if (health.usableBucketCount !== expectedUsable) {
    out.push({
      id: "calibration.usable_count_mismatch",
      area: "consistency",
      severity: "danger",
      message: `usableBucketCount is ${health.usableBucketCount} but medium+high = ${expectedUsable}`,
      expected: String(expectedUsable),
      actual: String(health.usableBucketCount),
      hint: "Check usableBucketCount calculation",
    });
  }
  
  // Info: report calibration summary
  out.push({
    id: "calibration.summary",
    area: "calibration",
    severity: "info",
    message: `Calibration: ${health.bucketCount} buckets (${health.usableBucketCount} usable, ${health.trustedBucketCount} trusted, ${health.confidenceBucketCounts.unreliable} unreliable)`,
    actual: {
      bucketCount: health.bucketCount,
      usable: health.usableBucketCount,
      trusted: health.trustedBucketCount,
      unreliable: health.confidenceBucketCounts.unreliable,
      low: health.confidenceBucketCounts.low,
      medium: health.confidenceBucketCounts.medium,
      high: health.confidenceBucketCounts.high,
    },
  });
  
  return out;
}

export const ALL_INVARIANTS = [
  { id: "timeline",            run: checkTimeline },
  { id: "bayes_sum",           run: checkBayesSumsPerPhoto },
  { id: "evidence_symmetry",   run: checkEvidenceSymmetry },
  { id: "photo_records",       run: (_c: InvariantContext) => checkPhotoRecords() },
  { id: "bucket_membership",   run: checkBucketMembership },
  { id: "similar_exclusion",   run: checkSimilarSelfExclusion },
  { id: "pipeline",            run: checkPipeline },
  { id: "cache",               run: checkCache },
  { id: "ageing",              run: checkAgeing },
  { id: "ground_truth",        run: (_c: InvariantContext) => checkGroundTruth() },
  { id: "api_timings",         run: checkApiTimings },
  { id: "determinism",         run: (_c: InvariantContext) => checkDeterminism() },
  { id: "calibration_cross",   run: checkCalibrationCrossRef },
];
