import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { EvidenceNote } from "../components/common/EvidenceStatus";
import { evidenceOf } from "../data/evidencePolicy";

interface Cluster {
  id: string;
  size: number;
  files: string[];
  urls: string[];
  years: (number | null)[];
  distinctYears: number[];
  yearSpan: number;
  isCrossYear: boolean;
  sha256s: string[];
  dhashes: string[];
  poseBucket: string;
}
interface ClusterReport {
  generatedAt: string;
  threshold: number;
  totalPhotos: number;
  clusterMode: string;
  poseBucketSummary: Record<string, { count: number; clusters: number; photosInClusters: number }>;
  pairCount: number;
  clusters: Cluster[];
  summary: {
    total: number;
    crossYear: number;
    sameYear: number;
    maxSize: number;
    maxYearSpan: number;
    photosInClusters: number;
  };
}

export default function ClustersPage() {
  const [data, setData] = useState<ClusterReport | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    fetch("/duplicate-clusters.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => (d ? setData(d) : setMissing(true)));
  }, []);

  if (missing) {
    return (
      <Page title="Визуальные кластеры">
        <PanelCard title="Нет отчёта о кластерах на диске">
          <div className="text-[11px] text-muted">
            Запустите <code className="text-white">npx tsx scripts/duplicate_clusters.ts --threshold 3</code>
            из <code className="text-white">ui/</code>. Скрипт читает <code>signal-report.json</code>
            и группирует фото через union-find по расстоянию dHash.
          </div>
        </PanelCard>
      </Page>
    );
  }
  if (!data) return <Page title="Визуальные кластеры"><div className="text-[11px] text-muted">Загрузка…</div></Page>;

  return (
    <Page
      title="Визуальные кластеры"
      subtitle={`${data.summary.total} кластеров · порог dHash ≤ ${data.threshold} · ${data.summary.photosInClusters} из ${data.totalPhotos} фото · кластеризация внутри групп ракурса`}
    >
      <EvidenceNote level={evidenceOf("visual_clusters")!.level} className="mb-3">
        <div><strong>Реальная часть:</strong> {evidenceOf("visual_clusters")!.realPart}</div>
        <div><strong>Ограничение:</strong> Фото с малым расстоянием dHash разделяют <em>композицию / ракурс / кадрирование</em>,
          а не обязательно содержание. Кластеризация выполнена <strong>внутри каждой группы ракурса</strong> (frontal, ¾-left, ¾-right, profile-left, profile-right),
          чтобы разделение шло по идентичности, а не по ракурсу.
          Обнаружение побайтовых дубликатов — на странице
          <span className="text-info"> Сигналы реальных фото</span>.</div>
        <div><strong>Для перехода:</strong> {evidenceOf("visual_clusters")!.upgradeHint}</div>
      </EvidenceNote>

      {/* Pose bucket summary */}
      {data.poseBucketSummary && (
        <PanelCard title="Распределение по ракурсам" className="mb-3">
          <table className="w-full text-[11px]">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-2">ракурс</th>
                <th className="text-left p-2">фото</th>
                <th className="text-left p-2">кластеры</th>
                <th className="text-left p-2">фото в кластерах</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.poseBucketSummary).map(([bucket, info]) => (
                <tr key={bucket} className="border-b border-line/30">
                  <td className="p-2 text-white">{bucket}</td>
                  <td className="p-2 font-mono text-white">{info.count}</td>
                  <td className="p-2 font-mono text-info">{info.clusters}</td>
                  <td className="p-2 font-mono text-muted">{info.photosInClusters}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelCard>
      )}

      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="всего кластеров" value={data.summary.total}            color="#cfd8e6" />
        <Stat label="межгодовые"     value={data.summary.crossYear}        color="#f59e0b" />
        <Stat label="макс. размер"       value={data.summary.maxSize}          color="#38bdf8" />
        <Stat label="макс. размах лет"  value={`${data.summary.maxYearSpan}г`} color="#a855f7" />
      </div>

      <div className="space-y-3">
        {data.clusters.map((c) => (
          <PanelCard
            key={c.id}
            title={`${c.id}  ·  ${c.poseBucket}  ·  размер ${c.size}  ·  размах ${c.yearSpan}г  ·  ${c.isCrossYear ? "межгодовой" : "внутригодовой"}`}
          >
            <div className="text-[10px] text-muted mb-2">
              годы: {c.distinctYears.length > 0 ? c.distinctYears.join(", ") : "без даты в имени"} ·
              dhashes: <span className="font-mono">{c.dhashes.join(" / ")}</span>
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-2">
              {c.files.map((f, i) => (
                <div key={f} className="bg-bg-deep rounded border border-line/60 overflow-hidden">
                  <img src={c.urls[i]} alt="" className="w-full aspect-square object-cover" loading="lazy" />
                  <div className="px-1 py-1 text-[10px]">
                    <div className="text-white font-mono truncate">{f}</div>
                    <div className="text-muted">год: {c.years[i] ?? "—"}</div>
                  </div>
                </div>
              ))}
            </div>
          </PanelCard>
        ))}
      </div>
    </Page>
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
