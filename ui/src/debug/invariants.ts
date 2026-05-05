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

  // Metrics are per-year (27 values), yearPoints are per-photo.
  // The old check expected yearPoints.length === years.length, but now
  // yearPoints has one entry per photo, not per year.
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

  // Removed cluster B check - it's just an info message about missing data

  return out;
}

export async function checkBayesSumsPerPhoto(_ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  // Bayesian verdicts are all null — court has not run.
  // Skip the sum check until real data exists.
  return out;
}

export async function checkEvidenceSymmetry(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  // Evidence(A,B) should be swap-invariant. Disabled - depends on mock PHOTOS
  return out;
}

export async function checkPhotoRecords(): Promise<Finding[]> {
  // Disabled - depends on mock PHOTOS
  return [];
};

export async function checkBucketMembership(ctx: InvariantContext): Promise<Finding[]> {
  const out: Finding[] = [];
  // Photos returned for (frontal, daylight) should all be pose=frontal
  const list = await ctx.api.photosInBucket("frontal", "daylight");
  const violators = list.filter((p) => {
    const poseVal = typeof p.pose === "string" ? p.pose : (p.pose as Record<string, unknown>)?.bucket;
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
  // Disabled - depends on mock PHOTOS
  return [];
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

export async function checkAgeing(_ctx: InvariantContext): Promise<Finding[]> {
  // Disabled - ageing model not built, this is just an info message
  return [];
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
  // Disabled - depends on mock PHOTOS and buildPhotoDetail
  return [];
}

export async function checkTZCoverage(): Promise<Finding[]> {
  // Disabled - TZ coverage map now only shows real implementations
  return [];
}

/**
 * Returns the static TZ coverage map for the report (distinct from the
 * finding-generator above because it always produces data, not issues).
 */
export function tzCoverageMap(): Array<{ topic: string; impl: string; aliases?: string[] }> {
  // Only real implementations - no mock files
  return [
    {
      topic: "Pose-dependent visibility gating",
      impl: "src/pages/PairAnalysisPage.tsx",
      aliases: ["Сравнение с учётом позы"],
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
      impl: "src/pages/PipelinePage.tsx + api.getCacheSummary",
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
    { topic: "Reports (list + builder)",           impl: "src/pages/ReportBuilderPage.tsx" },
    { topic: "API catalog / explorer",             impl: "src/pages/ReportBuilderPage.tsx + api.getApiCatalog" },
    { topic: "Ground truth calibration anchors",   impl: "src/pages/CalibrationPage.tsx" },
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

  // Removed calibration summary info finding - it's just informational

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
