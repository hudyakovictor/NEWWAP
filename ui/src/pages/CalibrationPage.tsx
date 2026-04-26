import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import Modal from "../components/common/Modal";
import { api, type CalibrationBucket, type CalibrationSummary } from "../api";
import type { PhotoRecord } from "../mock/photos";
import PhotoDetailModal from "../components/photo/PhotoDetailModal";

// Extended bucket type with person distribution from real data
type Level = CalibrationBucket["level"];
interface BucketWithPersons extends CalibrationBucket {
  personDistribution?: Record<string, number>;
}

const LEVEL_COLOR: Record<Level, string> = {
  unreliable: "#ef4444",
  low: "#f59e0b",
  medium: "#eab308",
  high: "#22c55e",
};

export default function CalibrationPage() {
  const [summary, setSummary] = useState<CalibrationSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<CalibrationBucket | null>(null);

  useEffect(() => {
    api.getCalibration().then((s) => {
      setSummary(s);
      setLoading(false);
    });
  }, []);

  if (loading || !summary) {
    return (
      <Page title="Calibration health" subtitle="Loading…">
        <div className="text-[11px] text-muted">Fetching calibration summary…</div>
      </Page>
    );
  }

  const { buckets, recommendations } = summary;
  const poses = Array.from(new Set(buckets.map((b) => b.pose)));
  const lights = Array.from(new Set(buckets.map((b) => b.light)));

  const totals = {
    high: buckets.filter((b) => b.level === "high").length,
    medium: buckets.filter((b) => b.level === "medium").length,
    low: buckets.filter((b) => b.level === "low").length,
    unreliable: buckets.filter((b) => b.level === "unreliable").length,
  };

  return (
    <Page
      title="Calibration health"
      subtitle="Self-healing bucket database · click any cell to drill down"
      actions={
        <button className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">
          Recompute metrics
        </button>
      }
    >
      <div className="grid grid-cols-4 gap-3 mb-3">
        {(Object.keys(totals) as Array<keyof typeof totals>).map((k) => (
          <PanelCard key={k} title={`${k} buckets`}>
            <div className="text-2xl font-semibold" style={{ color: LEVEL_COLOR[k as Level] }}>
              {totals[k]}
            </div>
            <div className="text-[11px] text-muted">of {buckets.length} total</div>
          </PanelCard>
        ))}
      </div>

      <PanelCard title="Bucket matrix" className="mb-3">
        <div className="overflow-auto">
          <table className="text-[11px] w-full">
            <thead>
              <tr className="text-muted border-b border-line">
                <th className="text-left p-1">pose \ light</th>
                {lights.map((l) => <th key={l} className="text-center p-1">{l}</th>)}
              </tr>
            </thead>
            <tbody>
              {poses.map((p) => (
                <tr key={p} className="border-b border-line/40">
                  <td className="p-1 text-white">{p}</td>
                  {lights.map((l) => {
                    const b = buckets.find((x) => x.pose === p && x.light === l)!;
                    return (
                      <td key={l} className="p-1 text-center">
                        <button
                          onClick={() => setSelected(b)}
                          className="inline-flex flex-col items-center gap-0.5 px-2 py-1 rounded hover:ring-2 hover:ring-info/50"
                          style={{ background: LEVEL_COLOR[b.level] + "30" }}
                          title={`variance ${b.variance}`}
                        >
                          <span className="font-mono" style={{ color: LEVEL_COLOR[b.level] }}>{b.count}</span>
                          <span className="text-[9px]" style={{ color: LEVEL_COLOR[b.level] }}>{b.level}</span>
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </PanelCard>

      <PanelCard title="Recommendations">
        <ul className="space-y-1 text-[11px]">
          {recommendations.map((r, i) => (
            <li
              key={i}
              className={r.severity === "danger" ? "text-danger" : r.severity === "warn" ? "text-warn" : "text-info"}
            >
              • {r.text}
            </li>
          ))}
        </ul>
      </PanelCard>

      {selected && <BucketDetailModal bucket={selected} onClose={() => setSelected(null)} />}
    </Page>
  );
}

function BucketDetailModal({
  bucket,
  onClose,
}: {
  bucket: CalibrationBucket;
  onClose: () => void;
}) {
  const [photos, setPhotos] = useState<PhotoRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [opened, setOpened] = useState<PhotoRecord | null>(null);

  useEffect(() => {
    api.photosInBucket(bucket.pose, bucket.light).then((r) => {
      setPhotos(r);
      setLoading(false);
    });
  }, [bucket.pose, bucket.light]);

  return (
    <Modal
      title={`Bucket: ${bucket.pose} / ${bucket.light}`}
      onClose={onClose}
      width="max-w-5xl"
    >
      <div className="grid grid-cols-4 gap-3 mb-3">
        <KV k="level" v={<span style={{ color: LEVEL_COLOR[bucket.level] }}>{bucket.level}</span>} />
        <KV k="sample count" v={bucket.count} />
        <KV k="variance" v={bucket.variance} />
        <KV k="strategy" v={strategyFor(bucket.level)} />
      </div>
      <div className="text-[11px] text-muted mb-2">
        {loading
          ? "Fetching photos…"
          : `${photos.length} photo(s) in this bucket (click to inspect, mark outliers)`}
      </div>
      <div className="grid grid-cols-8 gap-2">
        {photos.map((p) => (
          <button
            key={p.id}
            onClick={() => setOpened(p)}
            className="relative group rounded overflow-hidden border border-line hover:border-info"
          >
            <img src={p.photo} alt="" className="w-full aspect-square object-cover" />
            <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/90 to-transparent p-1">
              <div className="text-[9px] text-white font-mono">{p.date}</div>
              <div className="text-[9px] text-muted">{p.expression}</div>
            </div>
          </button>
        ))}
      </div>
      {opened && (
        <PhotoDetailModal
          photoId={opened.id}
          point={{
            year: opened.year,
            photo: opened.photo,
            identity: opened.cluster,
            anomaly: opened.flags.includes("silicone")
              ? "danger"
              : opened.flags.includes("anomaly")
              ? "warn"
              : undefined,
          }}
          onClose={() => setOpened(null)}
        />
      )}
    </Modal>
  );
}

function strategyFor(level: Level): string {
  if (level === "high") return "standard comparison thresholds";
  if (level === "medium") return "widened confidence intervals";
  if (level === "low") return "bone-only fallback weighting";
  return "excluded from runtime comparisons";
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="bg-bg-deep/70 border border-line/60 rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-muted">{k}</div>
      <div className="text-sm font-mono text-white">{v}</div>
    </div>
  );
}
