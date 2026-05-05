/**
 * Simplified module registry - only basic info without descriptions or levels
 */

export interface ModuleEvidence {
  id: string;
  label: string;
  pages: string[];
}

export const MODULE_EVIDENCE: ModuleEvidence[] = [
  { id: "photo_registry", label: "Реестр фото", pages: ["photos", "clusters", "signals"] },
  { id: "head_pose", label: "Определение ракурса", pages: ["photos", "timeline", "iterations", "pairs"] },
  { id: "bbox", label: "Ограничивающие рамки", pages: ["photos"] },
  { id: "face_stats", label: "Статистика кропов лица", pages: ["timeline", "iterations"] },
  { id: "signals", label: "Сигналы фото", pages: ["signals", "clusters"] },
  { id: "calibration_buckets", label: "Бакеты калибровки", pages: ["calibration"] },
  { id: "pair_comparison", label: "Попарное сравнение", pages: ["pairs", "matrix"] },
  { id: "comparison_matrix", label: "Матрица сходства", pages: ["matrix"] },
  { id: "ageing_curve", label: "Кривая старения", pages: ["ageing"] },
  { id: "timeline_metrics", label: "Метрики таймлайна", pages: ["timeline"] },
  { id: "anomalies", label: "Реестр аномалий", pages: ["anomalies"] },
  { id: "synthetic_detector", label: "Детектор синтетики", pages: ["pairs", "photos"] },
  { id: "bayesian_court", label: "Байесовский суд", pages: ["pairs", "report_builder"] },
  { id: "visual_clusters", label: "Визуальные кластеры", pages: ["clusters"] },
  { id: "identity_clusters", label: "Кластеры идентичности", pages: ["photos", "timeline"] },
  { id: "pipeline_stages", label: "Стадии конвейера", pages: ["pipeline", "progress"] },
  { id: "artifact_manifest", label: "Манифест артефактов", pages: ["progress"] },
  { id: "report_builder", label: "Конструктор отчётов", pages: ["report_builder"] },
];

const BY_ID = new Map(MODULE_EVIDENCE.map((m) => [m.id, m]));

export function evidenceOf(moduleId: string): ModuleEvidence | undefined {
  return BY_ID.get(moduleId);
}
