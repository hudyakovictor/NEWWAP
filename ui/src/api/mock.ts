import {
  YEARS,
  yearPoints,
  metrics,
  identitySegments,
  eventMarkers,
  photoVolume,
} from "../mock/data";
import { PHOTOS } from "../mock/photos";
import { buildPhotoDetail } from "../mock/photoDetail";
import { rngFor } from "../debug/prng";
import { getDhashIndex, dhashDistance } from "../debug/dhashIndex";
import { detectPoseAnomalies } from "../data/poseAnomalies";
import { MAIN_PHOTOS, MYFACE_PHOTOS, ALL_PHOTOS } from "../data/photoRegistry";
import { buildCalibrationBuckets, buildCalibrationHealth } from "../data/calibrationBuckets";
import FORENSIC_REGISTRY from "../data/forensic_registry.json";
import type {
  Backend,
  PhotoListQuery,
  Job,
  Investigation,
  AnomalyRecord,
  CalibrationBucket,
  PipelineStage,
  CacheSummary,
  CacheEntry,
  AgeingPoint,
  EvidenceBreakdown,
  ApiEndpoint,
  DiaryEntry,
} from "./types";

let jobs: Job[] = [
  {
    id: "job-001",
    kind: "extract",
    status: "done",
    progress: 1,
    total: 1742,
    processed: 1742,
    startedAt: "2025-04-20 12:00",
    finishedAt: "2025-04-20 14:32",
    note: "Full batch reconstruction complete",
    logs: [
      "[12:00:01] scanning storage/main …",
      "[12:00:03] 1742 photos queued",
      "[14:32:12] done, 1742 ok, 0 failed",
    ],
  },
  {
    id: "job-002",
    kind: "recompute_metrics",
    status: "done",
    progress: 1,
    total: 1742,
    processed: 1742,
    startedAt: "2025-04-21 09:10",
    finishedAt: "2025-04-21 09:52",
    logs: ["[09:10:00] loading calibration …", "[09:52:00] metrics written"],
  },
  {
    id: "job-003",
    kind: "calibrate",
    status: "failed",
    progress: 0.42,
    total: 1742,
    processed: 731,
    startedAt: "2025-04-23 18:20",
    finishedAt: "2025-04-23 18:41",
    note: "VRAM exhausted on large batch — reduce window size",
    logs: [
      "[18:20:00] starting calibration pass",
      "[18:41:02] CUDA OOM — reducing cache_size → 6",
      "[18:41:03] aborted after 731/1742",
    ],
  },
];

let investigations: Investigation[] = [
  {
    id: "inv-001",
    name: "DEEPUTIN full timeline",
    subject: "Subject 1",
    createdAt: "2025-04-10",
    updatedAt: "2025-04-24",
    photoCount: PHOTOS.length,
    verdict: "H1",
    notes: "Primary investigation — spans 1999–2025 with multiple suspected substitutions.",
    tags: ["primary", "public"],
  },
  {
    id: "inv-002",
    name: "2012 anomaly cluster",
    subject: "Subject 1",
    createdAt: "2025-04-18",
    updatedAt: "2025-04-22",
    photoCount: 58,
    verdict: "H1",
    notes: "Focused 2012–2014 window: silicone probability spike + bone asymmetry inversion.",
    tags: ["cluster", "priority"],
  },
  {
    id: "inv-003",
    name: "Cluster B audit",
    subject: "Subject 1",
    createdAt: "2025-04-20",
    updatedAt: "2025-04-24",
    photoCount: 432,
    verdict: "open",
    notes: "Review all photos tagged cluster_b (2015–2020).",
    tags: ["audit"],
  },
];

// Real calibration buckets from myface same-person pairs
const calibrationBuckets: CalibrationBucket[] = buildCalibrationBuckets();

// Build anomalies registry. Real entries first (driven by actual pose
// data), synthetic entries follow so the UI can show the real ones at the
// top of the list.
const anomalies: AnomalyRecord[] = [
  ...detectPoseAnomalies(),
  ...yearPoints
    .filter((p) => p.anomaly)
    .map((p, i) => ({
      id: `anom-y-${p.year}-${i}`,
      year: p.year,
      severity: p.anomaly!,
      kind: "chronology" as const,
      title: p.note ?? `Year-level anomaly in ${p.year}`,
      detectedAt: `${p.year}-06-15`,
      resolved: false,
    })),
  ...eventMarkers
    .filter((e) => e.kind === "warn" || e.kind === "danger" || e.kind === "info")
    .map((e, i) => ({
      id: `anom-e-${e.year}-${i}`,
      year: e.year,
      severity: e.kind === "danger" ? ("danger" as const) : e.kind === "warn" ? ("warn" as const) : ("info" as const),
      kind: "calibration" as const,
      title: e.title,
      detectedAt: `${e.year}-03-12`,
      resolved: false,
    })),
  ...PHOTOS.filter((p) => p.flags.includes("silicone"))
    .slice(0, 40)
    .map((p) => ({
      id: `anom-s-${p.id}`,
      year: p.year,
      severity: "danger" as const,
      kind: "synthetic" as const,
      photoId: p.id,
      title: `High silicone signature (${p.syntheticProb.toFixed(2)})`,
      detectedAt: p.date,
      resolved: false,
    })),
  ...PHOTOS.filter((p) => p.flags.includes("pose_fallback"))
    .slice(0, 15)
    .map((p) => ({
      id: `anom-p-${p.id}`,
      year: p.year,
      severity: "info" as const,
      kind: "pose" as const,
      photoId: p.id,
      title: "Primary pose detector fell back to 3DDFA-V3",
      detectedAt: p.date,
      resolved: true,
    })),
];

function delay<T>(v: T, ms = 30): Promise<T> {
  return new Promise((r) => setTimeout(() => r(v), ms));
}

export const mockBackend: Backend = {
  async getTimeline() {
    return delay({
      years: YEARS,
      yearPoints,
      metrics,
      identitySegments,
      eventMarkers,
      photoVolume,
      totalPhotos: PHOTOS.length,
      calibrationLevel: "medium",
    });
  },

  async listPhotos(q: PhotoListQuery) {
    let list = PHOTOS.slice();
    if (q.search) {
      const s = q.search.toLowerCase();
      list = list.filter((p) => p.id.includes(s) || p.date.includes(s));
    }
    if (q.pose && q.pose !== "any") list = list.filter((p) => p.pose === q.pose);
    if (q.expression && q.expression !== "any") list = list.filter((p) => p.expression === q.expression);
    if (q.source && q.source !== "any") list = list.filter((p) => p.source === q.source);
    if (q.flag && q.flag !== "any") list = list.filter((p) => p.flags.includes(q.flag as any));
    if (q.minSyntheticProb) list = list.filter((p) => p.syntheticProb >= q.minSyntheticProb!);
    if (q.sortBy === "synthetic") list.sort((a, b) => b.syntheticProb - a.syntheticProb);
    else if (q.sortBy === "bayes") list.sort((a, b) => a.bayesH0 - b.bayesH0);
    else list.sort((a, b) => (a.date < b.date ? -1 : 1));
    const total = list.length;
    const offset = q.offset ?? 0;
    const limit = q.limit ?? 500;
    return delay({ total, items: list.slice(offset, offset + limit) });
  },

  async getPhotoDetail(id: string) {
    const rec = PHOTOS.find((p) => p.id === id) ?? PHOTOS[0];
    const detail = buildPhotoDetail(rec.year, rec.photo);
    return delay({ ...detail, record: rec });
  },

  async similarPhotos(id: string, limit = 8) {
    const rec = PHOTOS.find((p) => p.id === id) ?? PHOTOS[0];
    // Make sure the dhash index is loaded so we can use real perceptual
    // distance whenever the photo URL is anchored to a real file.
    const idx = await getDhashIndex();
    const seedHash = idx.get(rec.photo);

    const scored = PHOTOS.filter((p) => p.id !== rec.id).map((p) => {
      // Synthetic baseline (kept as a fallback so non-anchored photos still
      // get a usable score).
      let synthetic = 1;
      synthetic -= Math.abs(p.bayesH0 - rec.bayesH0) * 0.4;
      synthetic -= Math.abs(p.syntheticProb - rec.syntheticProb) * 0.3;
      if (p.pose !== rec.pose) synthetic -= 0.2;
      if (p.cluster !== rec.cluster) synthetic -= 0.25;
      synthetic -= Math.abs(p.year - rec.year) / 50;

      // Real perceptual term when both photos point to a hashed file.
      let perceptual = 0;
      let usedDhash = false;
      const candHash = idx.get(p.photo);
      if (seedHash && candHash) {
        const d = dhashDistance(seedHash, candHash);
        // Map Hamming distance [0..32] → [1..0] linearly (clamped). A 64-bit
        // dHash rarely exceeds 32 for visually related portraits.
        perceptual = Math.max(0, 1 - d / 32);
        usedDhash = true;
      }

      // Weighted blend: when we have real dHash, trust it more (60/40);
      // otherwise pure synthetic.
      const score = usedDhash ? perceptual * 0.6 + synthetic * 0.4 : synthetic;
      return { p, score, usedDhash };
    });
    scored.sort((a, b) => b.score - a.score);
    return delay(scored.slice(0, limit).map((s) => s.p));
  },

  async getCalibration() {
    const health = buildCalibrationHealth();
    const recommendations = [];
    
    if (health.unusableBuckets.length > 0) {
      recommendations.push({
        severity: "warn" as const,
        text: `${health.unusableBuckets.length} buckets unreliable: ${health.unusableBuckets.slice(0, 3).join(", ")}${health.unusableBuckets.length > 3 ? "..." : ""}`,
      });
    }
    
    if (health.lowConfidenceBuckets.length > 0) {
      recommendations.push({
        severity: "info" as const,
        text: `${health.lowConfidenceBuckets.length} buckets need more samples`,
      });
    }
    
    if (health.readyForRuntimeBucketKeys.length > 0) {
      recommendations.push({
        severity: "info" as const,
        text: `${health.readyForRuntimeBucketKeys.length} buckets ready for runtime`,
      });
    }
    
    return delay({
      buckets: calibrationBuckets,
      recommendations,
    });
  },

  async photosInBucket(pose: string, light: string) {
    // Deterministic mock: pick photos where pose matches; light is synthetic
    const list = PHOTOS.filter((p) => p.pose === pose).slice(0, 60);
    // Apply a cheap "light" hash so different light → different subset
    const seed = light.length + pose.length;
    return delay(list.filter((_, i) => (i + seed) % 2 === 0));
  },

  async listJobs() {
    return delay(jobs.slice());
  },

  async startJob(kind: Job["kind"]) {
    const j: Job = {
      id: `job-${String(jobs.length + 1).padStart(3, "0")}`,
      kind,
      status: "running",
      progress: 0,
      total: 1742,
      processed: 0,
      startedAt: new Date().toISOString().slice(0, 16).replace("T", " "),
      logs: [`[${new Date().toISOString().slice(11, 19)}] job ${kind} queued`],
    };
    jobs = [j, ...jobs];
    // simulate progression
    const tick = () => {
      const cur = jobs.find((x) => x.id === j.id);
      if (!cur || cur.status !== "running") return;
      cur.progress = Math.min(1, cur.progress + 0.05);
      cur.processed = Math.round(cur.progress * cur.total);
      cur.logs = [
        ...(cur.logs ?? []),
        `[${new Date().toISOString().slice(11, 19)}] ${cur.processed}/${cur.total}`,
      ];
      if (cur.progress >= 1) {
        cur.status = "done";
        cur.finishedAt = new Date().toISOString().slice(0, 16).replace("T", " ");
        cur.logs!.push(`[${new Date().toISOString().slice(11, 19)}] completed`);
        return;
      }
      setTimeout(tick, 500);
    };
    setTimeout(tick, 200);
    return delay(j);
  },

  async listInvestigations() {
    return delay(investigations.slice());
  },

  async upsertInvestigation(i: Investigation) {
    const idx = investigations.findIndex((x) => x.id === i.id);
    if (idx >= 0) investigations[idx] = i;
    else investigations = [i, ...investigations];
    return delay(i);
  },

  async deleteInvestigation(id: string) {
    investigations = investigations.filter((x) => x.id !== id);
    return delay(undefined as void);
  },

  async listAnomalies() {
    return delay(anomalies.slice());
  },

  async getPipelineStages() {
    // Real pipeline progress derived from actual pose runs + signal scan.
    // Stages downstream of pose are still stub.
    const total = ALL_PHOTOS.length;
    const withPose = ALL_PHOTOS.filter((p) => p.pose.source !== "none").length;
    const noPose = ALL_PHOTOS.filter((p) => p.pose.source === "none").length;
    const hpeShare = ALL_PHOTOS.filter((p) => p.pose.source === "hpe").length;
    const ddfaShare = ALL_PHOTOS.filter((p) => p.pose.source === "3ddfa").length;
    const regCount = Object.keys(FORENSIC_REGISTRY).length;
    const stages: PipelineStage[] = [
      {
        id: "ingest",
        name: "Ingest & file scan (real)",
        order: 1,
        inputCount: total,
        outputCount: total,
        failed: 0,
        avgMs: 0,
        notes: `${MAIN_PHOTOS.length} main + ${MYFACE_PHOTOS.length} myface (5 myface non-portraits filtered upstream)`,
      },
      {
        id: "signal",
        name: "Perceptual signals (real)",
        order: 2,
        inputCount: total,
        outputCount: total,
        failed: 0,
        avgMs: 50,
        notes: "SHA-256 + JPEG dimensions + 8×8 dHash per file",
      },
      {
        id: "pose",
        name: "Head-pose (HPE primary + 3DDFA-V3 fallback) (real)",
        order: 3,
        inputCount: total,
        outputCount: withPose,
        failed: noPose,
        avgMs: 320,
        gpuMemoryMB: 2100,
        notes: `${hpeShare} via HPE + ${ddfaShare} via 3DDFA fallback · ${noPose} unresolved`,
      },
      {
        id: "pose_aggregate",
        name: "Pose stats per year (real)",
        order: 4,
        inputCount: withPose,
        outputCount: withPose,
        failed: 0,
        avgMs: 1,
        notes: "Mean |yaw|, frontal ratio, pose distribution per year",
      },
      // Real downstream stages
      { id: "recon",       name: "3DDFA_v3 reconstruction (real)", order: 5, inputCount: withPose, outputCount: regCount, failed: withPose - regCount, avgMs: 1450, notes: `Processed ${regCount} passports` },
      { id: "zones",       name: "21-zone extraction (real)",      order: 6, inputCount: regCount, outputCount: regCount, failed: 0, avgMs: 15 },
      { id: "texture",     name: "Texture FFT/LBP/albedo (real)",  order: 7, inputCount: regCount, outputCount: regCount, failed: 0, avgMs: 45 },
      { id: "calibration", name: "Calibration bucket (stub)",       order: 8, inputCount: 0, outputCount: 0, failed: 0, avgMs: 0 },
      { id: "bayes",       name: "Bayesian synthesis (stub)",       order: 9, inputCount: 0, outputCount: 0, failed: 0, avgMs: 0 },
    ];
    return delay(stages);
  },

  async getCacheSummary() {
    const r = (n: number) => Math.floor(Math.abs(Math.sin(n * 991.1) * 0xffffff))
      .toString(16).padStart(6, "0");
    const sample = PHOTOS.slice(0, 10);
    const entries: CacheEntry[] = sample.map((p, i) => ({
      md5: p.md5 + r(i),
      photoId: p.id,
      year: p.year,
      neutral: i % 2 === 0,
      vramMB: 160 + (i * 13) % 90,
      createdAt: `${p.year}-04-21 ${String(10 + i).padStart(2, "0")}:00:00`,
      lastAccess: `${p.year}-04-24 ${String(10 + i).padStart(2, "0")}:${String(i * 5).padStart(2, "0")}:00`,
      hits: 1 + (i * 7) % 20,
    }));
    const summary: CacheSummary = {
      maxSize: 10,
      currentSize: entries.length,
      vramFootprintMB: entries.reduce((a, e) => a + e.vramMB, 0),
      vramBudgetMB: 4096,
      evictions: [
        { md5: "b7f2a91c", at: "2025-04-23 18:37:12", reason: "LRU: cache full" },
        { md5: "c88d1014", at: "2025-04-23 18:40:03", reason: "explicit free (VRAM guard)" },
        { md5: "3012aa77", at: "2025-04-24 09:10:00", reason: "neutral-variant swap" },
      ],
      entries,
    };
    return delay(summary);
  },

  async getAgeingSeries() {
    // fit: fittedAge = 46 + i
    const series: AgeingPoint[] = yearPoints.map((p, i) => {
      const fitted = 46 + i;
      // observed: usually close, jump for 2012 & 2014
      let observed = fitted + (Math.sin(i * 11.13) * 0.8);
      const anomaly = p.year === 2012 || p.year === 2014 || p.year === 2023;
      if (anomaly) observed += 4.5;
      const residual = +(observed - fitted).toFixed(2);
      return {
        year: p.year,
        observedAge: +observed.toFixed(2),
        fittedAge: fitted,
        residual,
        outlier: Math.abs(residual) > 2,
        note: anomaly ? "Observed age exceeds fitted normal aging by > 2σ — possible identity substitution or mask." : undefined,
      };
    });
    return delay(series);
  },

  async getEvidence(aId: string, bId: string) {
    const a = PHOTOS.find((p) => p.id === aId) ?? PHOTOS[0];
    const b = PHOTOS.find((p) => p.id === bId) ?? PHOTOS[1];
    const sameCluster = a.cluster === b.cluster;
    // Seed by ordered (smaller, larger) so evidence(A,B) === evidence(B,A) — a property
    // checked by the symmetry invariant.
    const [k1, k2] = [a.id, b.id].sort();
    const r = rngFor("evidence", k1, k2);
    const snr = sameCluster ? 0.78 + r() * 0.1 : 0.32 + r() * 0.15;
    const syn = Math.max(a.syntheticProb, b.syntheticProb);
    const boneScore = sameCluster ? 0.82 : 0.48;
    const ligScore = sameCluster ? 0.74 : 0.51;
    const softScore = 0.55;
    const deltaYears = Math.abs(a.year - b.year);
    const boneJump = sameCluster ? 0.12 : 0.64;
    const ligJump = sameCluster ? 0.09 : 0.58;
    const flags: string[] = [];
    if (!sameCluster) flags.push("Cluster mismatch between photos");
    if (syn > 0.5) flags.push("Synthetic signature on one side");
    if (deltaYears > 10 && !sameCluster) flags.push("Long temporal gap with cluster switch");

    const priors = { H0: 0.78, H1: 0.02, H2: 0.20 };
    const likelihoods = {
      H0: snr,
      H1: syn > 0.45 ? syn : 0.08,
      H2: 1 - snr,
    };
    const z =
      priors.H0 * likelihoods.H0 + priors.H1 * likelihoods.H1 + priors.H2 * likelihoods.H2 || 1;
    const post = {
      H0: +((priors.H0 * likelihoods.H0) / z).toFixed(3),
      H1: +((priors.H1 * likelihoods.H1) / z).toFixed(3),
      H2: +((priors.H2 * likelihoods.H2) / z).toFixed(3),
    };
    const verdict = (post.H0 >= post.H1 && post.H0 >= post.H2
      ? "H0"
      : post.H1 >= post.H2
      ? "H1"
      : "H2") as "H0" | "H1" | "H2";

    const br: EvidenceBreakdown = {
      aId: a.id,
      bId: b.id,
      geometric: {
        snr: +snr.toFixed(3),
        boneScore: +boneScore.toFixed(3),
        ligamentScore: +ligScore.toFixed(3),
        softTissueScore: +softScore.toFixed(3),
        zoneCount: 18,
        excludedZones: a.expression === "smile" || b.expression === "smile"
          ? ["texture_wrinkle_nasolabial", "nose_width_ratio"]
          : [],
        categoryDivergence: {
          bone: 0.05,
          ligament: 0.08,
          symmetry: 0.03,
          soft_tissue: 0.12,
        },
      },
      texture: {
        syntheticProb: +syn.toFixed(3),
        rawSyntheticProb: +Math.min(1, syn * 1.3).toFixed(3), // До корректировки естественностью
        naturalScore: 0.35, // Признаки естественной кожи
        fft: +(Math.max(a.syntheticProb, b.syntheticProb) * 0.8).toFixed(3),
        lbp: +(1 - Math.min(a.syntheticProb, b.syntheticProb) * 0.6).toFixed(3),
        albedo: +(0.75 - syn * 0.4).toFixed(3),
        specular: +(syn * 0.9).toFixed(3),
        textureFeatures: {
          silicone: +syn.toFixed(3),
          fft_anomaly: 0.45,
          albedo_uniformity: 0.62,
          specular_gloss: 0.38,
          lbp_uniformity: 0.55,
        },
        naturalMarkers: {
          pore_density: 42,
          lbp_complexity: 2.8,
          wrinkle_detail: 18,
        },
        epochAdjustments: {
          fft_boost: 0.05,
          silicone_threshold_boost: 0.02,
        },
        h1Subtype: {
          primary: syn > 0.4 ? "mask" : "uncertain",
          confidence: syn > 0.4 ? 0.72 : 0.35,
          scores: {
            mask: syn > 0.4 ? 0.65 : 0.25,
            deepfake: 0.20,
            prosthetic: syn > 0.3 ? 0.40 : 0.15,
            uncertain: syn > 0.4 ? 0.15 : 0.60,
          },
          indicators: syn > 0.4 ? ["high_specular_uniformity"] : ["insufficient_indicators"],
        },
      },
      chronology: {
        deltaYears,
        boneJump: +boneJump.toFixed(3),
        ligamentJump: +ligJump.toFixed(3),
        flags,
        longitudinal: {
          modelUsed: true,
          consistent: true,
          chronologicalLikelihood: 0.92,
          inconsistenciesCount: 0,
          note: "Temporal progression consistent with aging model",
        },
      },
      pose: {
        mutualVisibility: a.pose === b.pose ? 0.95 : 0.72,
        expressionExcluded:
          a.expression === "smile" || b.expression === "smile" ? 2 : 0,
        poseDistanceDeg: a.pose === b.pose ? 5 : 25,
      },
      dataQuality: {
        coverageRatio: 0.86,
        missingZonesA: [],
        missingZonesB: ["texture_spot_density"],
      },
      priors,
      likelihoods: {
        H0: +likelihoods.H0.toFixed(3),
        H1: +likelihoods.H1.toFixed(3),
        H2: +likelihoods.H2.toFixed(3),
        chronological: 0.92,
        components: {
          geometricH0: 0.85,
          geometricH2: 0.15,
          textureH1: 0.42,
        },
      },
      posteriors: post,
      verdict: verdict as "H0" | "H1" | "H2" | "INSUFFICIENT_DATA",
      methodologyVersion: "ITER-6.5-MOCK",
      computationLog: [
        "Methodology: ITER-6.5-MOCK",
        "Zones analyzed: 18/21 (coverage: 86%)",
        "Zones excluded due to expression: 2 (texture_wrinkle_nasolabial, nose_width_ratio)",
        "Missing metrics A: 0 zones, B: 1 zones",
        `Adaptive priors: H0=${priors.H0.toFixed(3)}, H1=${priors.H1.toFixed(3)}, H2=${priors.H2.toFixed(3)}`,
        `Structural SNR: ${(snr * 10).toFixed(1)} dB`,
        "Bone divergence: 0.050, Ligament: 0.080",
        "Texture H1 raw composite: 0.420",
        "Texture H1 natural score: 0.350",
        `Texture H1 adjusted: ${(syn * 0.7).toFixed(3)}, likelihood: ${likelihoods.H1.toFixed(3)}`,
        "Pose distance: 5.0°, mutual visibility: 0.95",
        `Time delta: ${deltaYears} years`,
        "Coverage penalty applied: 0.86",
        `Final posteriors: H0=${post.H0.toFixed(3)}, H1=${post.H1.toFixed(3)}, H2=${post.H2.toFixed(3)}`,
        `Verdict: ${verdict}`,
      ],
    };
    return delay(br);
  },

  async getApiCatalog() {
    const cat: ApiEndpoint[] = [
      {
        method: "GET",
        path: "/api/timeline",
        description: "Year-aggregated timeline (photo anchors, metric rows, identity segments, events, photo volume).",
        group: "debug",
        sampleResponse: {
          years: [1999, 2000, 2025],
          yearPoints: [{ year: 1999, identity: "A", anomaly: null, photo: "/photos/…" }],
          metrics: [{ id: "skull", kind: "line", values: [1.62, 1.63] }],
          identitySegments: [{ id: "A", from: 1999, to: 2014 }],
          eventMarkers: [{ year: 2012, kind: "danger", title: "Suspected identity swap" }],
          totalPhotos: 1742,
        },
      },
      {
        method: "GET",
        path: "/api/photos",
        description: "Filterable + sortable list of individual photo records.",
        group: "photos",
        sampleResponse: {
          total: 1742,
          items: [{ id: "main-20120730-00a", year: 2012, pose: "frontal", cluster: "A", flags: ["silicone"] }],
        },
      },
      {
        method: "GET",
        path: "/api/photos/{id}",
        description: "Full per-photo detail including 21 zones, 3D reconstruction artefacts, texture metrics, bayesian verdict, chronology flags, metadata.",
        group: "photos",
        sampleResponse: { id: "main-20120730-00a", zones: [{ id: "nasal_bridge", score: 0.91 }] },
      },
      {
        method: "GET",
        path: "/api/photos/{id}/similar",
        description: "Top-N nearest photos by pose + cluster + synthetic profile.",
        group: "photos",
        sampleResponse: { items: [{ id: "main-…", score: 0.82 }] },
      },
      {
        method: "POST",
        path: "/api/photos/upload",
        description: "Ingest new photos; returns job id for the extract pipeline.",
        group: "photos",
        sampleResponse: { accepted: 12, rejected: 0, jobId: "job-019" },
      },
      {
        method: "POST",
        path: "/api/pairs/evidence",
        description: "Full bayesian courtroom synthesis for a given (A, B) pair.",
        group: "pairs",
        sampleResponse: { posteriors: { H0: 0.12, H1: 0.65, H2: 0.23 }, verdict: "H1" },
      },
      {
        method: "POST",
        path: "/api/pairs/matrix",
        description: "N×N pairwise similarity matrix for a set of photo ids.",
        group: "pairs",
        sampleResponse: { ids: ["a", "b", "c"], matrix: [[1, 0.8, 0.3], [0.8, 1, 0.4], [0.3, 0.4, 1]] },
      },
      {
        method: "GET",
        path: "/api/calibration/summary",
        description: "Bucket matrix with confidence levels, sample counts, variance, and recommendations.",
        group: "calibration",
        sampleResponse: { buckets: [{ pose: "frontal", light: "daylight", level: "high", count: 540 }] },
      },
      {
        method: "GET",
        path: "/api/calibration/bucket",
        description: "List photos in a given calibration bucket (pose × light).",
        group: "calibration",
        sampleResponse: { pose: "frontal", light: "daylight", photoIds: ["main-…", "main-…"] },
      },
      {
        method: "GET",
        path: "/api/jobs",
        description: "Queue of pipeline jobs with status and progress.",
        group: "jobs",
        sampleResponse: { jobs: [{ id: "job-003", kind: "calibrate", status: "failed" }] },
      },
      {
        method: "POST",
        path: "/api/jobs",
        description: "Start a new pipeline job: extract / recompute_metrics / calibrate / reindex.",
        group: "jobs",
        sampleResponse: { id: "job-019", status: "running" },
      },
      {
        method: "GET",
        path: "/api/jobs/{id}/log",
        description: "Streaming log of a specific job.",
        group: "jobs",
        sampleResponse: { logs: ["[10:00:00] queued", "[10:00:02] 12/1742"] },
      },
      {
        method: "GET",
        path: "/api/cases",
        description: "Investigations / cases list.",
        group: "cases",
        sampleResponse: { items: [{ id: "inv-001", verdict: "H1" }] },
      },
      {
        method: "PUT",
        path: "/api/cases/{id}",
        description: "Create or update a case.",
        group: "cases",
        sampleResponse: { id: "inv-009", updatedAt: "2025-04-24" },
      },
      {
        method: "GET",
        path: "/api/anomalies",
        description: "Registry of all raised anomalies with severity, kind, resolution state.",
        group: "anomalies",
        sampleResponse: { items: [{ id: "anom-…", severity: "danger", kind: "synthetic" }] },
      },
      {
        method: "GET",
        path: "/api/debug/pipeline",
        description: "Per-stage diagnostics of the ingest pipeline.",
        group: "debug",
        sampleResponse: { stages: [{ id: "recon", inputCount: 1738, failed: 5, avgMs: 312 }] },
      },
      {
        method: "GET",
        path: "/api/debug/cache",
        description: "Reconstruction cache summary: keys, VRAM, eviction history.",
        group: "debug",
        sampleResponse: { maxSize: 10, currentSize: 10, evictions: [] },
      },
      {
        method: "GET",
        path: "/api/debug/ageing",
        description: "Fitted ageing curve with observed vs expected residuals and outlier flags.",
        group: "debug",
        sampleResponse: { items: [{ year: 2012, residual: 4.7, outlier: true }] },
      },
    ];
    return delay(cat);
  },

  async comparisonMatrix(ids: string[]) {
    const recs = ids.map((id) => PHOTOS.find((p) => p.id === id)).filter(Boolean) as typeof PHOTOS;
    const matrix = recs.map((a) =>
      recs.map((b) => {
        if (a.id === b.id) return 1;
        let s = 1;
        s -= Math.abs(a.bayesH0 - b.bayesH0) * 0.4;
        s -= Math.abs(a.syntheticProb - b.syntheticProb) * 0.3;
        if (a.pose !== b.pose) s -= 0.15;
        if (a.cluster !== b.cluster) s -= 0.3;
        s -= Math.abs(a.year - b.year) / 60;
        return +Math.max(0, Math.min(1, s)).toFixed(3);
      })
    );
    return delay(matrix);
  },

  async uploadPhotos(files: File[]) {
    const jobId = `job-${String(jobs.length + 1).padStart(3, "0")}`;
    jobs = [
      {
        id: jobId,
        kind: "extract",
        status: "running",
        progress: 0,
        total: files.length,
        processed: 0,
        startedAt: new Date().toISOString().slice(0, 16).replace("T", " "),
        note: `ingesting ${files.length} file(s)`,
        logs: files.map((f, i) => `[queued] ${i + 1}. ${f.name} (${(f.size / 1024).toFixed(1)} KB)`),
      },
      ...jobs,
    ];
    return delay({ accepted: files.length, rejected: 0, jobId });
  },

  /* diary / investigation notebook */
  async getDiaryEntries() {
    const entries = JSON.parse(localStorage.getItem("deepsort_diary") || "[]") as DiaryEntry[];
    const byStatus = {
      open: entries.filter((e) => e.type === "hypothesis" && e.status === "open").length,
      confirmed: entries.filter((e) => e.type === "hypothesis" && e.status === "confirmed").length,
      rejected: entries.filter((e) => e.type === "hypothesis" && e.status === "rejected").length,
      needs_data: entries.filter((e) => e.type === "hypothesis" && e.status === "needs_data").length,
    };
    return delay({ entries, total: entries.length, byStatus });
  },

  async addDiaryEntry(entry) {
    const entries = JSON.parse(localStorage.getItem("deepsort_diary") || "[]") as DiaryEntry[];
    const newEntry: DiaryEntry = { ...entry, id: `entry_${Date.now()}_${Math.random().toString(36).slice(2, 7)}` };
    entries.unshift(newEntry);
    localStorage.setItem("deepsort_diary", JSON.stringify(entries));
    return delay(newEntry);
  },

  async updateDiaryEntry(id, updates) {
    const entries = JSON.parse(localStorage.getItem("deepsort_diary") || "[]") as DiaryEntry[];
    const idx = entries.findIndex((e) => e.id === id);
    if (idx === -1) throw new Error("Entry not found");
    entries[idx] = { ...entries[idx], ...updates };
    localStorage.setItem("deepsort_diary", JSON.stringify(entries));
    return delay(entries[idx]);
  },
};
