import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";

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
}
interface ClusterReport {
  generatedAt: string;
  threshold: number;
  totalPhotos: number;
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
      <Page title="Visual clusters">
        <PanelCard title="No cluster report on disk">
          <div className="text-[11px] text-muted">
            Run <code className="text-white">npx tsx scripts/duplicate_clusters.ts --threshold 3</code>
            from <code className="text-white">ui/</code>. The script reads <code>signal-report.json</code>
            and groups photos via union-find on dHash distance.
          </div>
        </PanelCard>
      </Page>
    );
  }
  if (!data) return <Page title="Visual clusters"><div className="text-[11px] text-muted">Loading…</div></Page>;

  return (
    <Page
      title="Visual clusters"
      subtitle={`${data.summary.total} clusters · threshold dHash ≤ ${data.threshold} · ${data.summary.photosInClusters} of ${data.totalPhotos} photos in clusters`}
    >
      <PanelCard className="mb-3">
        <div className="text-[11px] text-warn leading-snug">
          <span className="font-semibold">⚠ What this page actually shows.</span>{" "}
          Photos with low dHash distance share <em>composition / pose / framing</em>,
          not necessarily content. Visual verification revealed that two genuinely
          different sessions of the same person in the same profile pose can land at
          dHash distance 2–3. Use this view for grouping, not for "mis-dated duplicate"
          claims. Byte-identical detection lives in the SHA-256 column on the
          <span className="text-info"> Real signals</span> page.
        </div>
      </PanelCard>

      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="clusters total" value={data.summary.total}            color="#cfd8e6" />
        <Stat label="cross-year"     value={data.summary.crossYear}        color="#f59e0b" />
        <Stat label="max size"       value={data.summary.maxSize}          color="#38bdf8" />
        <Stat label="max year span"  value={`${data.summary.maxYearSpan}y`} color="#a855f7" />
      </div>

      <div className="space-y-3">
        {data.clusters.map((c) => (
          <PanelCard
            key={c.id}
            title={`${c.id}  ·  size ${c.size}  ·  span ${c.yearSpan}y  ·  ${c.isCrossYear ? "cross-year" : "same-year"}`}
          >
            <div className="text-[10px] text-muted mb-2">
              years: {c.distinctYears.length > 0 ? c.distinctYears.join(", ") : "no-date filenames"} ·
              dhashes: <span className="font-mono">{c.dhashes.join(" / ")}</span>
            </div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-2">
              {c.files.map((f, i) => (
                <div key={f} className="bg-bg-deep rounded border border-line/60 overflow-hidden">
                  <img src={c.urls[i]} alt="" className="w-full aspect-square object-cover" loading="lazy" />
                  <div className="px-1 py-1 text-[10px]">
                    <div className="text-white font-mono truncate">{f}</div>
                    <div className="text-muted">year: {c.years[i] ?? "—"}</div>
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
