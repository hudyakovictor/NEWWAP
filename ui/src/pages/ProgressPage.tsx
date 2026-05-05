import { Page, PanelCard } from "../components/common/Page";
import {
  ALL_PHOTOS,
  MAIN_PHOTOS,
  MYFACE_PHOTOS,
} from "../data/photoRegistry";

interface Stage {
  id: string;
  name: string;
}

const STAGES: Stage[] = [
  { id: "ingest", name: "Photo ingest" },
  { id: "pose", name: "Head pose" },
  { id: "perceptual", name: "Perceptual hash" },
  { id: "bbox", name: "Face bounding boxes" },
  { id: "face_stats", name: "Face crop stats" },
  { id: "texture", name: "Texture detector" },
  { id: "bayes", name: "Bayesian courtroom" },
  { id: "ageing", name: "Chronological analysis" },
];

export default function ProgressPage() {
  return (
    <Page
      title="Прогресс"
      subtitle="Стадии анализа"
    >
      <div className="grid grid-cols-2 gap-3 mb-3">
        <Stat label="всего стадий" value={STAGES.length} color="#38bdf8" />
        <Stat label="фото в UI" value={ALL_PHOTOS.length} color="#a855f7" />
      </div>

      <PanelCard title="Наборы фото" className="mb-3">
        <FolderProgress label="main" photos={MAIN_PHOTOS} expectedTotal={1638} />
        <FolderProgress label="myface" photos={MYFACE_PHOTOS} expectedTotal={199} />
      </PanelCard>

      <PanelCard title="Стадии анализа">
        <div className="space-y-1">
          {STAGES.map((s) => (
            <div key={s.id} className="bg-bg-deep/70 border border-line/60 rounded p-2 text-white">
              {s.name}
            </div>
          ))}
        </div>
      </PanelCard>
    </Page>
  );
}

function FolderProgress({
  label,
  photos,
  expectedTotal,
}: {
  label: string;
  photos: any[];
  expectedTotal: number;
}) {
  const have = photos.length;
  const pct = expectedTotal > 0 ? (have / expectedTotal) * 100 : 0;
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

function Stat({ label, value, color }: { label: string; value: React.ReactNode; color: string }) {
  return (
    <div className="bg-bg-panel border border-line rounded p-2">
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}
