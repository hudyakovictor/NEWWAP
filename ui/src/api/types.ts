// Public API surface used by UI. A real backend client and the mock adapter
// both implement this interface, so switching between them is a one-liner.

export interface TimelineSummary {
  years: number[];
  yearPoints: YearPoint[];
  metrics: MetricConfig[];
  identitySegments: IdentitySegment[];
  eventMarkers: EventMarker[];
  photoVolume: number[];
  totalPhotos: number;
  calibrationLevel: "unreliable" | "low" | "medium" | "high";
}

export interface PhotoListQuery {
  pose?: string;
  expression?: string;
  source?: string;
  flag?: string;
  minSyntheticProb?: number;
  search?: string;
  sortBy?: "date" | "synthetic" | "bayes";
  limit?: number;
  offset?: number;
}

export interface PhotoListResult {
  total: number;
  items: PhotoRecord[];
}

export interface CalibrationBucket {
  pose: string;
  light: string;
  level: "unreliable" | "low" | "medium" | "high";
  count: number;
  variance: number;
}

export interface CalibrationSummary {
  buckets: CalibrationBucket[];
  recommendations: { severity: "info" | "warn" | "danger"; text: string }[];
}

export interface Job {
  id: string;
  kind: "extract" | "recompute_metrics" | "calibrate" | "reindex";
  status: "pending" | "running" | "done" | "failed";
  progress: number;
  total: number;
  processed: number;
  startedAt: string;
  finishedAt?: string;
  note?: string;
  logs?: string[];
}

export interface Investigation {
  id: string;
  name: string;
  subject: string;
  createdAt: string;
  updatedAt: string;
  photoCount: number;
  verdict: "H0" | "H1" | "H2" | "open";
  notes: string;
  tags: string[];
}

export interface AnomalyRecord {
  id: string;
  year: number;
  severity: "info" | "ok" | "warn" | "danger";
  kind: "chronology" | "synthetic" | "pose" | "cluster" | "calibration";
  photoId?: string;
  title: string;
  detectedAt: string;
  resolved: boolean;
}

/* -------- debug / diagnostics ------------------------------------------- */

export interface PipelineStage {
  id: string;
  name: string;
  order: number;
  inputCount: number;
  outputCount: number;
  failed: number;
  avgMs: number;
  lastError?: string;
  gpuMemoryMB?: number;
  notes?: string;
}

export interface CacheEntry {
  md5: string;
  photoId: string;
  year: number;
  neutral: boolean;
  vramMB: number;
  createdAt: string;
  lastAccess: string;
  hits: number;
}

export interface CacheSummary {
  maxSize: number;
  currentSize: number;
  vramFootprintMB: number;
  vramBudgetMB: number;
  evictions: Array<{ md5: string; at: string; reason: string }>;
  entries: CacheEntry[];
}

export interface AgeingPoint {
  year: number;
  observedAge: number;       // from metric
  fittedAge: number;         // from aging model
  residual: number;          // observed - fitted
  outlier: boolean;
  note?: string;
}

export interface EvidenceBreakdown {
  aId: string;
  bId: string;
  geometric: {
    snr: number;
    boneScore: number;
    ligamentScore: number;
    softTissueScore: number;
    zoneCount: number;
    excludedZones: string[];
    categoryDivergence: Record<string, number>;
  };
  texture: {
    syntheticProb: number;
    rawSyntheticProb?: number;
    naturalScore?: number;
    fft: number;
    fftSpectrumData?: number[]; // [FIX-C1] Real FFT spectrum from backend, 24 bins
    lbp: number;
    albedo: number;
    specular: number;
    textureFeatures: Record<string, number>;
    naturalMarkers?: Record<string, number>;
    epochAdjustments?: Record<string, number>;
    h1Subtype?: {
      primary: "mask" | "deepfake" | "prosthetic" | "uncertain";
      confidence: number;
      scores: Record<string, number>;
      indicators: string[];
    };
  };
  chronology: {
    deltaYears: number;
    boneJump: number;
    ligamentJump: number;
    flags: string[];
    longitudinal?: {
      modelUsed: boolean;
      consistent?: boolean;
      chronologicalLikelihood?: number | null;
      inconsistenciesCount?: number;
      note?: string;
    };
  };
  pose: {
    mutualVisibility: number;
    expressionExcluded: number;
    poseDistanceDeg: number;
  };
  dataQuality: {
    coverageRatio: number;
    missingZonesA: string[];
    missingZonesB: string[];
  };
  likelihoods: {
    H0: number;
    H1: number;
    H2: number;
    chronological?: number | null;
    components?: {
      geometricH0: number;
      geometricH2: number;
      textureH1: number;
    };
  };
  priors: { H0: number; H1: number; H2: number };
  posteriors: { H0: number; H1: number; H2: number };
  verdict: "H0" | "H1" | "H2" | "INSUFFICIENT_DATA";
  methodologyVersion?: string;
  computationLog?: string[];
}

export interface ApiEndpoint {
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  description: string;
  group: "photos" | "pairs" | "calibration" | "jobs" | "cases" | "anomalies" | "debug";
  sampleResponse: unknown;
}

/* diary / investigation notebook */

export type HypothesisStatus = "open" | "confirmed" | "rejected" | "needs_data";

export interface DiaryEntry {
  id: string;
  content: string;
  type: "observation" | "hypothesis" | "conclusion";
  status?: HypothesisStatus;
  timestamp: string;
  relatedPhotos?: string[];
  relatedPairs?: string[];
}

export interface DiarySummary {
  entries: DiaryEntry[];
  total: number;
  byStatus: Record<HypothesisStatus, number>;
}

/* ------------------------------------------------------------------------- */

export interface Backend {
  getTimeline(): Promise<TimelineSummary>;
  listPhotos(q: PhotoListQuery): Promise<PhotoListResult>;
  getPhotoDetail(id: string): Promise<PhotoDetail & { record: PhotoRecord }>;
  similarPhotos(id: string, limit?: number): Promise<PhotoRecord[]>;
  getCalibration(): Promise<CalibrationSummary>;
  photosInBucket(pose: string, light: string): Promise<PhotoRecord[]>;
  listJobs(): Promise<Job[]>;
  startJob(kind: Job["kind"], options?: { dataset?: "main" | "calibration"; onlyIds?: string[]; limit?: number; metricKeys?: string[] }): Promise<Job>;
  listInvestigations(): Promise<Investigation[]>;
  upsertInvestigation(i: Investigation): Promise<Investigation>;
  deleteInvestigation(id: string): Promise<void>;
  listAnomalies(): Promise<AnomalyRecord[]>;
  uploadPhotos(files: File[]): Promise<{ accepted: number; rejected: number; jobId: string }>;

  /* debug / diagnostics */
  getPipelineStages(): Promise<PipelineStage[]>;
  getCacheSummary(): Promise<CacheSummary>;
  getAgeingSeries(): Promise<AgeingPoint[]>;
  getEvidence(aId: string, bId: string): Promise<EvidenceBreakdown>;
  getApiCatalog(): Promise<ApiEndpoint[]>;
  comparisonMatrix(ids: string[]): Promise<number[][]>;

  /* diary / investigation notebook */
  getDiaryEntries(): Promise<DiarySummary>;
  addDiaryEntry(entry: Omit<DiaryEntry, "id">): Promise<DiaryEntry>;
  updateDiaryEntry(id: string, updates: Partial<DiaryEntry>): Promise<DiaryEntry>;
}

// ─── Типы, перенесённые из mock/ ──────────────────────────────────────────
export type Severity = "ok" | "info" | "warn" | "danger";

export interface PhotoRecord {
  photo_id: string;
  id: string;
  filename: string;
  folder: string;
  year: number;
  date_str: string;
  bucket: string;
  pose: {
    yaw: number | null;
    pitch: number | null;
    roll: number | null;
    classification: string;
    source: string;
  } | null;
  syntheticProb: number | null;
  bayesH0: number | null;
  photo: string;
  cluster: string | null;
  flags: string[];
  identity: string | null;
  expression: string | null;
  source: string | null;
  md5: string | null;
  resolution: string | null;
  yaw: number | null;
  poseSource: string | null;
  date: string;
  [key: string]: any;
}

export interface FaceZone {
  id: string;
  name: string;
  group: "bone" | "ligament" | "soft";
  priority: "max" | "high" | "medium" | "low";
  weight: number;
}

export const FACE_ZONES: FaceZone[] = [
  { id: "forehead", name: "Forehead", group: "bone", priority: "max", weight: 1 },
  { id: "nasal_bridge", name: "Nasal Bridge", group: "bone", priority: "max", weight: 1 },
  { id: "orbital_l", name: "Left Orbital", group: "bone", priority: "high", weight: 1 },
  { id: "orbital_r", name: "Right Orbital", group: "bone", priority: "high", weight: 1 },
  { id: "cheek_l", name: "Left Cheek", group: "soft", priority: "medium", weight: 0.5 },
  { id: "cheek_r", name: "Right Cheek", group: "soft", priority: "medium", weight: 0.5 },
];

export interface YearPoint {
  year: number;
  photo: string;
  photoId: string;
  anomaly: Severity | null;
  identity: string | null;
  note: string | null;
  pose: {
    classification: string;
    yaw: number | null;
    pitch: number | null;
    source: string;
  } | null;
}

export type PhotoPoint = YearPoint;

export interface MetricConfig {
  key: string;
  label: string;
  domain?: [number, number];
  values: number[];
  flags?: (string | undefined)[];
  color?: string;
}

export interface IdentitySegment {
  from: number;
  to: number;
  identity: string;
  confidence: number;
}

export interface EventMarker {
  year: number;
  label: string;
  severity: Severity;
}

export interface PhotoDetail {
  year: number;
  photo: string;
  reconstruction: any;
  zones: any[];
  pose: any;
  expression: any;
  texture: any;
  calibration: any;
  chronology: any;
  bayes: any;
  meta: any;
  notes: string[];
}
