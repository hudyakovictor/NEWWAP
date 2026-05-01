import { Page, PanelCard } from "../components/common/Page";
import {
  ALL_PHOTOS,
  MAIN_PHOTOS,
  MYFACE_PHOTOS,
  poseDistribution,
  sourceDistribution,
  type RealPhoto,
} from "../data/photoRegistry";
import { EvidenceBadge, EvidenceNote } from "../components/common/EvidenceStatus";

/**
 * High-level progress dashboard: which analyses are real, which are still
 * stubs, and how much of each photo set has been processed.
 *
 * This page reads only from the bundled JSON via the photo registry —
 * fully synchronous, no network calls.
 */

interface Stage {
  id: string;
  name: string;
  status: "real" | "partial" | "stub";
  description: string;
  /** Optional per-folder progress (done / total). */
  progress?: { folder: string; done: number; total: number; note?: string }[];
  /** Pointer to the script / file that produces the data. */
  source?: string;
}

const STAGES: Stage[] = [
  {
    id: "ingest",
    name: "Photo ingest",
    status: "real",
    description: "Real photos accessible to the UI through symlinked / copied folders under ui/public.",
    progress: [
      { folder: "main", done: MAIN_PHOTOS.length, total: 1638 },
      { folder: "myface", done: MYFACE_PHOTOS.length, total: 199, note: "5 non-portraits filtered out" },
    ],
  },
  {
    id: "pose",
    name: "Head pose (yaw/pitch/roll)",
    status: "real",
    description:
      "core/runner_hpe.py primary, core/runner_3ddfa_v3.py fallback via scripts/poses_*_safe.py wrappers.",
    source: "scripts/poses_hpe_safe.py + scripts/poses_3ddfa_safe.py",
    progress: [
      mkPoseProgress("main", MAIN_PHOTOS),
      mkPoseProgress("myface", MYFACE_PHOTOS),
    ],
  },
  {
    id: "perceptual",
    name: "Perceptual hash (dHash) + SHA-256",
    status: "real",
    description:
      "scripts/signals.ts run on the full 1837 photo set. dHash 8×8 captures composition (not identity); use SHA-256 column for byte-identical detection.",
    source: "scripts/signals.ts → public/signal-report.json",
  },
  {
    id: "bbox",
    name: "Face bounding boxes (SCRFD)",
    status: "partial",
    description:
      "Per-photo face bbox + 5 facial keypoints from SCRFD. SCRFD detects 1387 of 1837 photos (76%); the remaining 450 had pose recovered via 3DDFA fallback but bbox is missing for them.",
    source: "scripts/bbox_safe.py → storage/bbox/",
    progress: [
      { folder: "main", done: 1211, total: 1638 },
      { folder: "myface", done: 176, total: 199 },
    ],
  },
  {
    id: "face_stats",
    name: "Face crop luminance + colour stats",
    status: "partial",
    description:
      "Mean/std luminance, mean/std RGB on the face crop. Only available for photos with a SCRFD bbox (1387 photos).",
    source: "scripts/face_stats.py → storage/face_stats/",
    progress: [
      { folder: "main", done: 1211, total: 1638 },
      { folder: "myface", done: 176, total: 199 },
    ],
  },
  {
    id: "reconstruction",
    name: "3D reconstruction (3DDFA_v3 mesh + UV)",
    status: "stub",
    description:
      "Only one test photo (1999_09_03) has reconstruction artifacts in storage/main/. Need batch run on full set.",
    source: "core/runner_3ddfa_v3.py with extractTex flags",
  },
  {
    id: "zones",
    name: "21-zone scoring",
    status: "stub",
    description: "UI shows synthetic zone scores. Need real per-photo zone extraction wired to mesh artifacts.",
  },
  {
    id: "texture",
    name: "Texture / synthetic-material detector",
    status: "partial",
    description:
      "Integrated real Laplacian-variance detector in backend/pipeline/texture.py. Requires real face crops to compute synthetic probability.",
    source: "pipeline/texture.py :: analyze_texture_synthetic_prob",
  },
  {
    id: "bayes",
    name: "Bayesian courtroom (H0 / H1 / H2)",
    status: "partial",
    description:
      "Logic implemented in backend/core/analysis.py and wired to /api/evidence/compare. Currently returns real results for processed pairs, falls back to 404 for unprocessed data.",
    source: "core/analysis.py :: calculate_bayesian_evidence",
  },
  {
    id: "ageing",
    name: "Chronological narrative engine",
    status: "partial",
    description: "Chronology analysis (detecting bone jumps and skips) implemented in backend/core/chronology.py. Awaiting integration with timeline UI.",
    source: "core/chronology.py :: analyze_chronology",
  },
  {
    id: "calibration",
    name: "Calibration buckets (pose × lighting)",
    status: "stub",
    description:
      "Bucket counts are mock. Real calibration will derive from myface (199 portraits) once cross-pose pair logic is defined.",
  },
];

function mkPoseProgress(folder: "main" | "myface", photos: RealPhoto[]): {
  folder: string;
  done: number;
  total: number;
  note?: string;
} {
  const sources = sourceDistribution(photos);
  const real = sources.hpe + sources["3ddfa"];
  const total = photos.length;
  const note =
    `HPE ${sources.hpe} + 3DDFA ${sources["3ddfa"]}` +
    (sources.none ? ` · ${sources.none} unresolved` : "");
  return { folder, done: real, total, note };
}

export default function ProgressPage() {
  const realCount = STAGES.filter((s) => s.status === "real").length;
  const partialCount = STAGES.filter((s) => s.status === "partial").length;
  const stubCount = STAGES.filter((s) => s.status === "stub").length;
  const overall = (realCount + 0.5 * partialCount) / STAGES.length;

  return (
    <Page
      title="Прогресс"
      subtitle={`${(overall * 100).toFixed(0)}% стадий анализа реальны (${realCount}/${STAGES.length}). Остальные — заглушки.`}
    >
      <EvidenceNote level="partial" className="mb-3">
        Эта панель оценивает готовность платформы, а не доказывает гипотезы. Финальные forensic-выводы допустимы только
        для стадий со статусом «реальные данные» и после массового извлечения признаков.
      </EvidenceNote>

      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="реальных стадий"    value={realCount}                                color="#22c55e" />
        <Stat label="частичных стадий" value={partialCount}                              color="#f59e0b" />
        <Stat label="стадий-заглушек"    value={stubCount}                                 color="#6b7a90" />
        <Stat label="фото в UI"   value={`${ALL_PHOTOS.length} (main+myface)`}      color="#38bdf8" />
      </div>

      <PanelCard title="Наборы фото" className="mb-3">
        <FolderProgress label="main (rebucketed_photos/all)" photos={MAIN_PHOTOS} expectedTotal={1638} />
        <FolderProgress label="myface (calibration)" photos={MYFACE_PHOTOS} expectedTotal={199} />
      </PanelCard>

      <PanelCard title="Распределение ракурсов (реальные)" className="mb-3">
        <PoseTable label="main"   photos={MAIN_PHOTOS} />
        <div className="h-2" />
        <PoseTable label="myface" photos={MYFACE_PHOTOS} />
      </PanelCard>

      <PanelCard title="Стадии анализа">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">стадия</th>
              <th className="text-left p-2">статус</th>
              <th className="text-left p-2">описание</th>
              <th className="text-left p-2">прогресс</th>
            </tr>
          </thead>
          <tbody>
            {STAGES.map((s) => (
              <tr key={s.id} className="border-b border-line/40 align-top">
                <td className="p-2 text-white font-semibold">{s.name}</td>
                <td className="p-2">
                  <StatusBadge status={s.status} />
                  <div className="mt-1">
                    <EvidenceBadge level={s.status === "real" ? "real" : s.status === "partial" ? "partial" : "stub"} />
                  </div>
                </td>
                <td className="p-2 text-muted">{s.description}</td>
                <td className="p-2">
                  {s.progress ? (
                    <div className="space-y-1 min-w-[220px]">
                      {s.progress.map((p) => {
                        const pct = p.total > 0 ? (p.done / p.total) * 100 : 0;
                        return (
                          <div key={p.folder}>
                            <div className="flex justify-between text-muted">
                              <span>{p.folder}</span>
                              <span className="font-mono text-white">
                                {p.done}/{p.total} · {pct.toFixed(0)}%
                              </span>
                            </div>
                            <div className="h-1.5 bg-bg rounded overflow-hidden">
                              <div
                                className="h-full"
                                style={{
                                  width: `${pct}%`,
                                  background: pct >= 100 ? "#22c55e" : pct > 0 ? "#38bdf8" : "#6b7a90",
                                }}
                              />
                            </div>
                            {p.note && <div className="text-[10px] text-muted">{p.note}</div>}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                  {s.source && <div className="text-[10px] text-muted mt-1">↳ {s.source}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>
    </Page>
  );
}

function StatusBadge({ status }: { status: Stage["status"] }) {
  const cfg =
    status === "real"
      ? { color: "#22c55e", label: "real" }
      : status === "partial"
      ? { color: "#f59e0b", label: "partial" }
      : { color: "#6b7a90", label: "stub" };
  return (
    <span
      className="text-[10px] px-1.5 py-0.5 rounded font-mono"
      style={{ background: cfg.color + "30", color: cfg.color }}
    >
      {cfg.label}
    </span>
  );
}

function FolderProgress({
  label,
  photos,
  expectedTotal,
}: {
  label: string;
  photos: RealPhoto[];
  expectedTotal: number;
}) {
  const have = photos.length;
  const pct = (have / expectedTotal) * 100;
  return (
    <div className="my-2">
      <div className="flex justify-between text-[11px]">
        <span className="text-white">{label}</span>
        <span className="font-mono text-muted">
          {have}/{expectedTotal} · {pct.toFixed(0)}%
        </span>
      </div>
      <div className="h-2 bg-bg rounded overflow-hidden">
        <div
          className="h-full"
          style={{ width: `${pct}%`, background: pct >= 100 ? "#22c55e" : "#38bdf8" }}
        />
      </div>
    </div>
  );
}

function PoseTable({ label, photos }: { label: string; photos: RealPhoto[] }) {
  const dist = poseDistribution(photos);
  const total = photos.length || 1;
  return (
    <div>
      <div className="text-[11px] text-muted mb-1">{label} ({photos.length} photos)</div>
      <div className="grid grid-cols-6 gap-1 text-[10px]">
        {(["frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right", "none"] as const).map(
          (k) => {
            const n = dist[k];
            const pct = (n / total) * 100;
            return (
              <div key={k} className="bg-bg-deep border border-line/60 rounded p-1">
                <div className="text-muted">{k.replace(/_/g, " ")}</div>
                <div className="text-white font-mono">{n}</div>
                <div className="text-muted">{pct.toFixed(1)}%</div>
              </div>
            );
          }
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: React.ReactNode; color: string }) {
  return (
    <div className="bg-bg-panel border border-line rounded p-2">
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}
