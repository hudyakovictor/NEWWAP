/**
 * Centralized evidence policy — single source of truth about which data
 * fields and pipeline outputs are real, partial, stub, or pending.
 *
 * Every page should consult this module (or the EvidenceBadge/EvidenceNote
 * components that wrap it) instead of hardcoding its own status logic.
 *
 * When a real pipeline run fills a field, update the entry here and the
 * change propagates to every page that references it.
 */

import type { EvidenceLevel } from "../components/common/EvidenceStatus";

/* ------------------------------------------------------------------ */
/*  Module-level evidence descriptors                                  */
/* ------------------------------------------------------------------ */

export interface ModuleEvidence {
  /** Machine-readable key used by pages. */
  id: string;
  /** Human-readable Russian name. */
  label: string;
  /** Current evidence level. */
  level: EvidenceLevel;
  /** What is real right now. */
  realPart: string;
  /** What is still stub / pending. */
  stubPart: string;
  /** What pipeline step must complete to upgrade the level. */
  upgradeHint: string;
  /** Which page(s) display this module's output. */
  pages: string[];
}

/**
 * The master registry.  Update this table when a pipeline run lands.
 */
export const MODULE_EVIDENCE: ModuleEvidence[] = [
  /* ---- photo / pose ------------------------------------------------ */
  {
    id: "photo_registry",
    label: "Реестр фото",
    level: "real",
    realPart: "1638 main + 199 myface фото с реальными путями и датами из имён файлов",
    stubPart: "—",
    upgradeHint: "Уже на максимальном уровне",
    pages: ["photos", "clusters", "signals"],
  },
  {
    id: "head_pose",
    label: "Определение ракурса (HPE + 3DDFA)",
    level: "real",
    realPart: "1638/1638 main (1211 HPE + 427 3DDFA) и 199/204 myface (176 HPE + 23 3DDFA) — yaw/pitch/roll + классификация",
    stubPart: "5 myface фото без детекции (не-портреты)",
    upgradeHint: "Уже на максимальном уровне для текущего датасета",
    pages: ["photos", "timeline", "iterations", "pairs"],
  },
  {
    id: "bbox",
    label: "Ограничивающие рамки (SCRFD)",
    level: "partial",
    realPart: "1387/1837 фото имеют bbox (76% покрытия)",
    stubPart: "450 фото без bbox — SCRFD не обнаружил лицо (3DDFA нашёл, но bbox нет)",
    upgradeHint: "Запустить bbox на 3DDFA-кадрах с увеличенным padding",
    pages: ["photos"],
  },
  {
    id: "face_stats",
    label: "Статистика кропов лица",
    level: "partial",
    realPart: "1387/1837 фото: meanLum, stdLum, RGB-каналы, размер кропа",
    stubPart: "450 фото без face stats (те же, что без bbox)",
    upgradeHint: "Зависит от bbox pipeline",
    pages: ["timeline", "iterations"],
  },
  {
    id: "signals",
    label: "Сигналы фото (SHA-256, dHash, размеры)",
    level: "real",
    realPart: "1837 фото: SHA-256, JPEG-размеры, dHash, средняя яркость, побайтовые дубликаты, ближайшие dHash-пары",
    stubPart: "—",
    upgradeHint: "Уже на максимальном уровне",
    pages: ["signals", "clusters"],
  },

  /* ---- calibration / comparison ------------------------------------ */
  {
    id: "calibration_buckets",
    label: "Бакеты калибровки (ракурс × освещение)",
    level: "partial",
    realPart: "5×5 матрица бакетов с реальным числом фото и pose-классификацией",
    stubPart: "Осветительная ось — заглушка (нет реальных метаданных освещения). Уровень надёжности бакета — эвристика, не расчёт дисперсии.",
    upgradeHint: "Извлечь реальную освещённость из EXIF или по анализу яркости кропа; рассчитать реальную дисперсию внутри бакета",
    pages: ["calibration"],
  },
  {
    id: "pair_comparison",
    label: "Попарное сравнение (геометрия + текстура)",
    level: "stub",
    realPart: "Реальные Δyaw/Δpitch/Δroll и взаимная видимость зон (на основе yaw-порогов ±55°)",
    stubPart: "21-zone bone scores, ligament scores, soft tissue scores — заглушки. SNR, texture FFT, LBP, albedo, specular — заглушки. Байесовские вероятности — заглушки.",
    upgradeHint: "Запустить 3D-реконструкцию → извлечь 21 зону → рассчитать геометрические и текстурные метрики → байесовский вывод",
    pages: ["pairs", "matrix"],
  },
  {
    id: "comparison_matrix",
    label: "Матрица N×N сходства",
    level: "insufficient",
    realPart: "—",
    stubPart: "Матрица рассчитана только по ракурсу и году. Нет текстурных, геометрических или кластерных компонент.",
    upgradeHint: "Зависит от pair_comparison pipeline",
    pages: ["matrix"],
  },

  /* ---- ageing / timeline ------------------------------------------- */
  {
    id: "ageing_curve",
    label: "Кривая старения",
    level: "insufficient",
    realPart: "—",
    stubPart: "Нет данных. Ранее были PRNG-заглушки — удалены. Модель старения не построена.",
    upgradeHint: "Рассчитать реальный наблюдаемый возраст из геометрических метрик (bone drift, soft tissue change); подогнать нелинейную модель старения",
    pages: ["ageing"],
  },
  {
    id: "timeline_metrics",
    label: "Метрики таймлайна",
    level: "real",
    realPart: "5 реальных рядов: фото/год, средний |yaw|/год, доля фронтальных/год, средняя яркость кропа/год, σ яркости/год",
    stubPart: "—",
    upgradeHint: "Уже на максимальном уровне для текущего pipeline. Добавление новых метрик (bone drift, texture) потребует новых pipeline-расчётов.",
    pages: ["timeline"],
  },

  /* ---- anomalies / forensic ---------------------------------------- */
  {
    id: "anomalies",
    label: "Реестр аномалий",
    level: "partial",
    realPart: "Сигналы: SHA-256 дубликаты (danger). Pose: extreme yaw >80° (info), 3DDFA-fallback (info), drift Δyaw>60° (warn). Флаг pose_fallback — реальный.",
    stubPart: "Синтетические хронологические и кластерные аномалии удалены. Флаги silicone удалены (syntheticProb = null).",
    upgradeHint: "Рассчитать реальные кластерные и хронологические флаги после pipeline расчёта",
    pages: ["anomalies"],
  },
  {
    id: "synthetic_detector",
    label: "Детектор синтетики (маски / deepfake / протез)",
    level: "insufficient",
    realPart: "—",
    stubPart: "Поле syntheticProb = null для всех фото без записи в forensic_registry. Нет реального детектора.",
    upgradeHint: "Обучить/подключить реальный детектор синтетики (FFT + LBP + нейросетевой классификатор)",
    pages: ["pairs", "photos"],
  },
  {
    id: "bayesian_court",
    label: "Байесовский суд (H0/H1/H2)",
    level: "insufficient",
    realPart: "—",
    stubPart: "Поля bayesH0 и cluster = null для всех фото. Вердикт — детерминированная эвристика в mock.ts, не реальный байесовский вывод.",
    upgradeHint: "Рассчитать реальные likelihoods из геометрических и текстурных метрик; задать обоснованные априори",
    pages: ["pairs", "report_builder"],
  },

  /* ---- identity / clusters ------------------------------------------ */
  {
    id: "visual_clusters",
    label: "Визуальные кластеры (dHash union-find)",
    level: "real",
    realPart: "Реальные кластеры на dHash-расстояниях из signal-report.json. Корректное предупреждение: dHash = композиция, не идентичность.",
    stubPart: "—",
    upgradeHint: "Уже на максимальном уровне для данного метода. Для идентичности нужен face embedding.",
    pages: ["clusters"],
  },
  {
    id: "identity_clusters",
    label: "Кластеры идентичности (A/B)",
    level: "insufficient",
    realPart: "—",
    stubPart: "Поле cluster = null для всех фото. Нет реальных face embeddings. Ранее была эвристика по году (2015-2020 = B) — удалена как вводящая в заблуждение.",
    upgradeHint: "Рассчитать face embeddings → кластеризация → реальное разделение",
    pages: ["photos", "timeline"],
  },

  /* ---- pipeline / infrastructure ------------------------------------ */
  {
    id: "pipeline_stages",
    label: "Стадии конвейера",
    level: "partial",
    realPart: "Ingest → Signals → Pose → Bbox → FaceStats — реальные стадии с реальными счётчиками",
    stubPart: "3D Reconstruction, 21-Zone, Texture, Synthetic Detector, Bayesian — заглушки с нулевым прогрессом",
    upgradeHint: "Запустить каждую стадию по очереди",
    pages: ["pipeline", "progress"],
  },
  {
    id: "artifact_manifest",
    label: "Манифест артефактов (версия / хеш / дата)",
    level: "stub",
    realPart: "—",
    stubPart: "Нет отслеживания версии артефактов. При повторном запуске pipeline невозможно отличить свежий результат от устаревшего.",
    upgradeHint: "Создать manifest.json с хешем исходных данных, конфигурацией модели и датой расчёта для каждого артефакта",
    pages: ["progress"],
  },

  /* ---- report / export --------------------------------------------- */
  {
    id: "report_builder",
    label: "Конструктор отчётов",
    level: "stub",
    realPart: "—",
    stubPart: "Сохранённые отчёты — хардкод. Предпросмотр — JSON с заглушками вместо реальных данных. Нет верификации целостности.",
    upgradeHint: "После заполнения реальных метрик — генерировать отчёт из актуальных данных с манифестом артефактов",
    pages: ["report_builder"],
  },
];

/* ------------------------------------------------------------------ */
/*  Helper lookups                                                     */
/* ------------------------------------------------------------------ */

const BY_ID = new Map(MODULE_EVIDENCE.map((m) => [m.id, m]));

/** Get the evidence level for a module by its id. */
export function evidenceLevelOf(moduleId: string): EvidenceLevel {
  return BY_ID.get(moduleId)?.level ?? "stub";
}

/** Get the full descriptor for a module. */
export function evidenceOf(moduleId: string): ModuleEvidence | undefined {
  return BY_ID.get(moduleId);
}

/** All modules at a given level. */
export function modulesAtLevel(level: EvidenceLevel): ModuleEvidence[] {
  return MODULE_EVIDENCE.filter((m) => m.level === level);
}

/** Summary counts per level. */
export function evidenceSummary(): Record<EvidenceLevel, number> {
  const out: Record<EvidenceLevel, number> = { real: 0, partial: 0, stub: 0, insufficient: 0, pending: 0 };
  for (const m of MODULE_EVIDENCE) out[m.level]++;
  return out;
}

/** Overall readiness score (0–100). Weighted: real=100, partial=55, stub=10, insufficient=0, pending=20. */
export function readinessScore(): number {
  const weights: Record<EvidenceLevel, number> = { real: 100, partial: 55, stub: 10, insufficient: 0, pending: 20 };
  const total = MODULE_EVIDENCE.reduce((a, m) => a + weights[m.level], 0);
  return Math.round(total / MODULE_EVIDENCE.length);
}
