/**
 * Artifact manifest — tracks version, source hash, model config, and
 * computation date for every pipeline output.  When a pipeline is
 * re-run, the manifest is updated so the UI can distinguish fresh
 * results from stale ones.
 *
 * This module is the single source of truth for artifact provenance.
 * Pages consult it to show computation dates and to flag stale data.
 */

export interface ArtifactEntry {
  /** Machine-readable key matching evidencePolicy module id. */
  id: string;
  /** Human-readable Russian name. */
  label: string;
  /** Pipeline stage that produced this artifact. */
  pipelineStage: string;
  /** When this artifact was last computed (ISO 8601 or descriptive). */
  computedAt: string;
  /** Hash or version tag of the input data used. */
  inputVersion: string;
  /** Model / algorithm version used for computation. */
  modelVersion: string;
  /** Number of records in the output. */
  recordCount: number;
  /** File path (relative to project root) where the artifact lives. */
  path: string;
  /** Whether the artifact is real (computed) or stub. */
  isReal: boolean;
  /** Short Russian note about the artifact. */
  note: string;
}

/**
 * The master manifest.  Update entries when a pipeline run completes.
 */
export const ARTIFACT_MANIFEST: ArtifactEntry[] = [
  {
    id: "photo_registry",
    label: "Реестр фото",
    pipelineStage: "ingest",
    computedAt: "2026-04-25T02:00",
    inputVersion: "rebucketed_photos/all + myface (204 files)",
    modelVersion: "filename-parser v1",
    recordCount: 1837,
    path: "ui/public/photos_main/ + ui/public/photos_myface/",
    isReal: true,
    note: "Символические ссылки на реальные фото. Даты из имён файлов.",
  },
  {
    id: "head_pose",
    label: "Определение ракурса",
    pipelineStage: "pose",
    computedAt: "2026-04-25T04:30",
    inputVersion: "photo_registry v1",
    modelVersion: "SCRFD + MobileNetV3 (HPE) + 3DDFA_v3 (fallback)",
    recordCount: 1837,
    path: "storage/poses/poses_main_consolidated.json + poses_myface_consolidated.json",
    isReal: true,
    note: "100% покрытие main, 97.5% myface. 5 myface записей — не-портреты.",
  },
  {
    id: "signals",
    label: "Сигналы фото",
    pipelineStage: "signals",
    computedAt: "2026-04-25T02:30",
    inputVersion: "photo_registry v1",
    modelVersion: "sha256 + dHash 8×8 + JPEG dimensions",
    recordCount: 1837,
    path: "ui/public/signal-report.json",
    isReal: true,
    note: "SHA-256, dHash, размеры, средняя яркость. 5 побайтовых дубликатов.",
  },
  {
    id: "bbox",
    label: "Ограничивающие рамки",
    pipelineStage: "bbox",
    computedAt: "2026-04-25T06:45",
    inputVersion: "photo_registry v1",
    modelVersion: "SCRFD (same as HPE detector)",
    recordCount: 1387,
    path: "storage/bbox/bbox_main.json + bbox_myface.json",
    isReal: true,
    note: "76% покрытие. 450 фото без bbox — SCRFD не обнаружил лицо.",
  },
  {
    id: "face_stats",
    label: "Статистика кропов лица",
    pipelineStage: "face_stats",
    computedAt: "2026-04-25T07:00",
    inputVersion: "bbox v1",
    modelVersion: "OpenCV meanStdDev on face crop",
    recordCount: 1387,
    path: "storage/face_stats/face_stats_main.json + face_stats_myface.json",
    isReal: true,
    note: "meanLum, stdLum, RGB каналы, размер кропа. Зависит от bbox.",
  },
  {
    id: "visual_clusters",
    label: "Визуальные кластеры",
    pipelineStage: "signals (post-process)",
    computedAt: "2026-04-25T06:00",
    inputVersion: "signals v1",
    modelVersion: "union-find on dHash distance ≤ 3",
    recordCount: 0,
    path: "ui/public/duplicate-clusters.json",
    isReal: true,
    note: "Кластеры визуально-похожих фото. dHash = композиция, не идентичность.",
  },
  {
    id: "calibration_buckets",
    label: "Бакеты калибровки",
    pipelineStage: "calibration",
    computedAt: "—",
    inputVersion: "—",
    modelVersion: "—",
    recordCount: 25,
    path: "backend: /api/calibration",
    isReal: false,
    note: "5×5 матрица pose×light. Pose — реально, light — заглушка. Дисперсия — эвристика.",
  },
  {
    id: "pair_comparison",
    label: "Попарное сравнение",
    pipelineStage: "compare",
    computedAt: "—",
    inputVersion: "—",
    modelVersion: "—",
    recordCount: 0,
    path: "backend: /api/evidence/{aId}/{bId}",
    isReal: false,
    note: "Δyaw/Δpitch/Δroll — реальные. 21-zone, SNR, texture, байес — заглушки.",
  },
  {
    id: "comparison_matrix",
    label: "Матрица N×N",
    pipelineStage: "compare (batch)",
    computedAt: "—",
    inputVersion: "—",
    modelVersion: "—",
    recordCount: 0,
    path: "backend: /api/comparison-matrix",
    isReal: false,
    note: "Все значения — PRNG-заглушки.",
  },
  {
    id: "ageing_curve",
    label: "Кривая старения",
    pipelineStage: "ageing",
    computedAt: "—",
    inputVersion: "—",
    modelVersion: "—",
    recordCount: 27,
    path: "backend: /api/ageing",
    isReal: false,
    note: "Модель 1 yr/yr. Наблюдаемые возраста — PRNG. Выбросы — артефакт заглушек.",
  },
  {
    id: "synthetic_detector",
    label: "Детектор синтетики",
    pipelineStage: "texture",
    computedAt: "—",
    inputVersion: "—",
    modelVersion: "—",
    recordCount: 0,
    path: "—",
    isReal: false,
    note: "syntheticProb — PRNG-заглушка. Нет реального детектора.",
  },
  {
    id: "bayesian_court",
    label: "Байесовский суд",
    pipelineStage: "bayes",
    computedAt: "—",
    inputVersion: "—",
    modelVersion: "—",
    recordCount: 0,
    path: "—",
    isReal: false,
    note: "Априори и апостериори — PRNG. Вердикт — эвристика.",
  },
  {
    id: "identity_clusters",
    label: "Кластеры идентичности",
    pipelineStage: "cluster",
    computedAt: "—",
    inputVersion: "—",
    modelVersion: "—",
    recordCount: 0,
    path: "—",
    isReal: false,
    note: "A/B — эвристика по году. Нет реальных face embeddings.",
  },
  {
    id: "report_builder",
    label: "Конструктор отчётов",
    pipelineStage: "export",
    computedAt: "—",
    inputVersion: "—",
    modelVersion: "—",
    recordCount: 4,
    path: "—",
    isReal: false,
    note: "Сохранённые отчёты — хардкод. Предпросмотр — JSON с заглушками.",
  },
];

const BY_ID = new Map(ARTIFACT_MANIFEST.map((a) => [a.id, a]));

/** Look up an artifact by its id. */
export function artifactOf(id: string): ArtifactEntry | undefined {
  return BY_ID.get(id);
}

/** All real artifacts. */
export function realArtifacts(): ArtifactEntry[] {
  return ARTIFACT_MANIFEST.filter((a) => a.isReal);
}

/** All stub artifacts. */
export function stubArtifacts(): ArtifactEntry[] {
  return ARTIFACT_MANIFEST.filter((a) => !a.isReal);
}

/** Count of real vs stub artifacts. */
export function artifactCounts(): { real: number; stub: number; total: number } {
  const real = ARTIFACT_MANIFEST.filter((a) => a.isReal).length;
  return { real, stub: ARTIFACT_MANIFEST.length - real, total: ARTIFACT_MANIFEST.length };
}
