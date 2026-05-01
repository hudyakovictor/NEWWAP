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

// Build anomalies registry. Only real entries from the pose pipeline.
// Synthetic year-based, event-based, and silicone anomalies have been
// removed — they were derived from PRNG stubs that no longer exist.
const anomalies: AnomalyRecord[] = [
  ...detectPoseAnomalies(),
  ...PHOTOS.filter((p) => p.flags.includes("pose_fallback"))
    .slice(0, 15)
    .map((p) => ({
      id: `anom-p-${p.id}`,
      year: p.year,
      severity: "info" as const,
      kind: "pose" as const,
      photoId: p.id,
      title: "Основной детектор ракурса переключился на 3DDFA-V3",
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
    if (q.minSyntheticProb) list = list.filter((p) => (p.syntheticProb ?? 0) >= q.minSyntheticProb!);
    if (q.sortBy === "synthetic") list.sort((a, b) => (b.syntheticProb ?? 0) - (a.syntheticProb ?? 0));
    else if (q.sortBy === "bayes") list.sort((a, b) => (a.bayesH0 ?? 0) - (b.bayesH0 ?? 0));
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
    // Use real perceptual distance (dHash) when available, plus
    // real pose similarity and temporal proximity.
    const idx = await getDhashIndex();
    const seedHash = idx.get(rec.photo);

    const scored = PHOTOS.filter((p) => p.id !== rec.id).map((p) => {
      // Real perceptual term when both photos point to a hashed file.
      let perceptual = 0;
      let usedDhash = false;
      const candHash = idx.get(p.photo);
      if (seedHash && candHash) {
        const d = dhashDistance(seedHash, candHash);
        perceptual = Math.max(0, 1 - d / 32);
        usedDhash = true;
      }

      // Real pose similarity
      let poseScore = 0.5;
      if (p.pose === rec.pose) poseScore = 1;
      else if (p.pose && rec.pose) {
        // Same bucket family (e.g. both 3/4)
        const pClass = p.pose.replace(/_(left|right)/, "");
        const rClass = rec.pose.replace(/_(left|right)/, "");
        if (pClass === rClass) poseScore = 0.7;
      }

      // Temporal proximity (closer years = more relevant)
      const yearDist = Math.abs(p.year - rec.year);
      const temporalScore = Math.max(0, 1 - yearDist / 30);

      // Weighted blend: dHash 60%, pose 25%, temporal 15%
      const score = usedDhash
        ? perceptual * 0.6 + poseScore * 0.25 + temporalScore * 0.15
        : poseScore * 0.55 + temporalScore * 0.45;

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
    // Only return calibration (myface) photos for bucket inspection
    const list = PHOTOS.filter((p) => p.folder === "myface" && p.pose === pose).slice(0, 60);
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
    // No real ageing model has been computed yet.
    // Previously this returned PRNG-fabricated observed/fitted ages.
    return delay([] as AgeingPoint[]);
  },

  async getEvidence(aId: string, bId: string) {
    const a = PHOTOS.find((p) => p.id === aId) ?? PHOTOS[0];
    const b = PHOTOS.find((p) => p.id === bId) ?? PHOTOS[1];
    const deltaYears = Math.abs(a.year - b.year);

    // Bayesian courtroom has not run — all numeric fields are fabricated.
    // Return INSUFFICIENT_DATA verdict with only real fields populated.
    const br: EvidenceBreakdown = {
      aId: a.id,
      bId: b.id,
      geometric: {
        snr: 0,
        boneScore: 0,
        ligamentScore: 0,
        softTissueScore: 0,
        zoneCount: 0,
        excludedZones: [],
        categoryDivergence: {},
      },
      texture: {
        syntheticProb: 0,
        fft: 0,
        lbp: 0,
        albedo: 0,
        specular: 0,
        textureFeatures: {},
      },
      chronology: {
        deltaYears,
        boneJump: 0,
        ligamentJump: 0,
        flags: [],
      },
      pose: {
        mutualVisibility: a.pose === b.pose ? 0.95 : 0.72,
        expressionExcluded: 0,
        poseDistanceDeg: a.pose === b.pose ? 5 : 25,
      },
      dataQuality: {
        coverageRatio: 0,
        missingZonesA: [],
        missingZonesB: [],
      },
      priors: { H0: 0, H1: 0, H2: 0 },
      likelihoods: { H0: 0, H1: 0, H2: 0 },
      posteriors: { H0: 0, H1: 0, H2: 0 },
      verdict: "INSUFFICIENT_DATA",
      methodologyVersion: "NONE",
      computationLog: [
        "Байесовский суд не запускался — данных для вердикта недостаточно.",
        `Разница в годах: ${deltaYears}`,
        `Ракурс A: ${a.pose}, ракурс B: ${b.pose}`,
        "Для запуска анализа необходимы: zone scores, texture metrics, bayesian priors.",
      ],
    };
    return delay(br);
  },

  async getApiCatalog() {
    const cat: ApiEndpoint[] = [
      {
        method: "GET",
        path: "/api/timeline",
        description: "Year-aggregated timeline (photo anchors, real metric rows, photo volume).",
        group: "debug",
        sampleResponse: {
          years: [1999, 2000, 2025],
          yearPoints: [{ year: 1999, identity: null, anomaly: null, photo: "/photos/…" }],
          metrics: [{ id: "real_count", kind: "bar", values: [42, 38] }],
          identitySegments: [],
          eventMarkers: [],
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
          items: [{ id: "main-20120730-00a", year: 2012, pose: "frontal", cluster: null, flags: [] }],
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
    // Use only real fields: pose similarity + temporal proximity
    const matrix = recs.map((a) =>
      recs.map((b) => {
        if (a.id === b.id) return 1;
        let s = 1;
        if (a.pose !== b.pose) s -= 0.15;
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
