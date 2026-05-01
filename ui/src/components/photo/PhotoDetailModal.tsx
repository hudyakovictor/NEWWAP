import { useEffect, useMemo, useState } from "react";
import { buildPhotoDetail } from "../../mock/photoDetail";
import type { YearPoint } from "../../mock/data";
import FaceZoneMap from "./FaceZoneMap";
import MeshViewer from "./MeshViewer";
import { api } from "../../api";
import { MAIN_PHOTOS } from "../../data/photoRegistry";
import type { PhotoRecord } from "../../mock/photos";
import { useApp } from "../../store/appStore";
import { log, getAllLogs, subscribe, type LogEntry } from "../../debug/logger";
import { validatePhotoDetail } from "../../debug/validators";
import { rngFor } from "../../debug/prng";

const tabs = [
  { id: "overview", label: "Overview" },
  { id: "reconstruction", label: "3D Reconstruction" },
  { id: "zones", label: "21 zones" },
  { id: "texture", label: "Texture & synthetic" },
  { id: "pose", label: "Pose & expression" },
  { id: "chronology", label: "Chronology" },
  { id: "calibration", label: "Calibration" },
  { id: "similar", label: "Similar photos" },
  { id: "audit_trail", label: "Audit trail" },
  { id: "meta", label: "Metadata" },
] as const;

type TabId = (typeof tabs)[number]["id"];

export default function PhotoDetailModal({
  point,
  photoId,
  photoUrl,
  year: propYear,
  onClose,
  onPrev,
  onNext,
}: {
  point?: YearPoint;
  photoId?: string;
  photoUrl?: string;
  year?: number;
  onClose: () => void;
  onPrev?: () => void;
  onNext?: () => void;
}) {
  // Support both old interface (point) and new interface (photoUrl + year)
  const effectivePhotoUrl = photoUrl || point?.photo || "";
  const effectiveYear = propYear || point?.year || 2000;
  const effectiveIdentity = point?.identity || "A";
  
  const [currentPhotoId, setCurrentPhotoId] = useState<string>(effectivePhotoUrl);

  useEffect(() => {
    setCurrentPhotoId(effectivePhotoUrl);
  }, [effectivePhotoUrl]);

  const detail = useMemo(() => buildPhotoDetail(effectiveYear, currentPhotoId), [effectiveYear, currentPhotoId]);
  const [tab, setTab] = useState<TabId>("overview");
  const [hoveredZone, setHoveredZone] = useState<string | undefined>();
  const { openPairWith } = useApp();

  const yearPhotos = useMemo(() => {
    return MAIN_PHOTOS.filter(p => p.year === effectiveYear).sort((a,b) => (a.date||"").localeCompare(b.date||""));
  }, [effectiveYear]);

  useEffect(() => {
    log.info("photo", "photo:modal_open", `Open detail for ${effectiveYear}`, { year: effectiveYear, photoId });
    const violations = validatePhotoDetail(detail);
    if (violations.length) {
      log.validation(
        "photo:modal_open:validate",
        `PhotoDetail for ${effectiveYear} has ${violations.length} violations`,
        { year: effectiveYear, photoId, detail },
        violations
      );
    }
    return () => {
      log.debug("photo", "photo:modal_close", `Close detail for ${effectiveYear}`, { year: effectiveYear, photoId });
    };
  }, [effectiveYear, photoId, detail]);

  useEffect(() => {
    log.trace("photo", "photo:tab", `tab → ${tab}`, { year: effectiveYear, tab });
  }, [tab, effectiveYear]);

  const compare = (slot: "A" | "B") => {
    if (photoId) {
      openPairWith(photoId, slot);
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full h-full max-w-[1600px] max-h-[95vh] bg-bg-panel border border-line rounded-lg shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* header */}
        <div className="flex flex-col border-b border-line shrink-0 bg-bg-panel/95 backdrop-blur-md">
          <div className="flex items-center h-12 px-4 shrink-0">
          <div className="flex items-center gap-3">
            <img src={detail.photo} alt="" className="w-9 h-9 rounded object-cover border border-line" />
            <div>
              <div className="text-sm font-semibold text-white">
                {detail.meta.filename}
              </div>
              <div className="text-[10px] text-muted">
                {detail.year} · {detail.meta.resolution} · {detail.meta.source} · cluster{" "}
                <span className={effectiveIdentity === "A" ? "text-accent" : "text-danger"}>
                  {effectiveIdentity}
                </span>
              </div>
            </div>
          </div>

          <div className="mx-auto flex items-center gap-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 h-7 text-[11px] rounded-md ${
                  tab === t.id ? "bg-line text-white" : "text-muted hover:text-white hover:bg-line/60"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-1">
            {photoId && (
              <>
                <button
                  onClick={() => compare("A")}
                  className="px-2 h-7 text-[11px] rounded bg-ok/70 hover:bg-ok text-white"
                  title="Set as Photo A in Pair analysis"
                >
                  Compare as A
                </button>
                <button
                  onClick={() => compare("B")}
                  className="px-2 h-7 text-[11px] rounded bg-accent/70 hover:bg-accent text-white mr-2"
                  title="Set as Photo B in Pair analysis"
                >
                  Compare as B
                </button>
              </>
            )}
            {onPrev && (
              <button
                onClick={onPrev}
                className="w-7 h-7 rounded bg-line/60 hover:bg-line text-white"
                title="Previous year"
              >
                ‹
              </button>
            )}
            {onNext && (
              <button
                onClick={onNext}
                className="w-7 h-7 rounded bg-line/60 hover:bg-line text-white"
                title="Next year"
              >
                ›
              </button>
            )}
            <button
              onClick={onClose}
              className="w-7 h-7 rounded bg-danger/30 hover:bg-danger/60 text-white ml-2"
              title="Close"
            >
              ×
            </button>
          </div>
        </div>

        {/* YEAR GALLERY */}
        {yearPhotos.length > 1 && (
          <div className="flex items-center gap-2 px-4 py-2 bg-bg-deep/50 overflow-x-auto scrollbar-thin border-b border-line/40 shrink-0">
            <span className="text-[10px] uppercase text-muted tracking-widest shrink-0 mr-2">All {effectiveYear} photos ({yearPhotos.length}):</span>
            <div className="flex gap-1">
              {yearPhotos.map(p => {
                const isActive = currentPhotoId.includes(p.id) || currentPhotoId === p.url;
                return (
                  <button 
                    key={p.id}
                    onClick={() => setCurrentPhotoId(p.url)}
                    title={`${p.date || 'Unknown date'} - ${p.pose.classification}`}
                    className={`shrink-0 w-10 h-10 rounded overflow-hidden border-2 transition-all ${isActive ? 'border-accent shadow-[0_0_8px_rgba(56,189,248,0.5)]' : 'border-transparent opacity-50 hover:opacity-100 hover:border-line'}`}
                  >
                    <img src={p.url} className="w-full h-full object-cover" />
                  </button>
                );
              })}
            </div>
          </div>
        )}
        </div>

        {/* body */}
        <div className="flex-1 overflow-auto p-4">
          {tab === "overview" && (
            <Overview detail={detail} hovered={hoveredZone} onHover={setHoveredZone} identity={effectiveIdentity} />
          )}
          {tab === "reconstruction" && <Reconstruction detail={detail} />}
          {tab === "zones" && (
            <Zones detail={detail} hovered={hoveredZone} onHover={setHoveredZone} />
          )}
          {tab === "texture" && <Texture detail={detail} />}
          {tab === "pose" && <PoseAndExpression detail={detail} />}
          {tab === "chronology" && <Chronology detail={detail} />}
          {tab === "calibration" && <CalibrationTab detail={detail} />}
          {tab === "similar" && <SimilarTab photoId={photoId} />}
          {tab === "audit_trail" && <AuditTrailTab year={effectiveYear} photoId={photoId} />}
          {tab === "meta" && <Meta detail={detail} />}
        </div>
      </div>
    </div>
  );
}

/* ----- Tabs ----- */

type D = ReturnType<typeof buildPhotoDetail>;

function Panel({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-bg-deep/60 border border-line/70 rounded-md p-3 ${className}`}>
      <div className="text-[10px] uppercase tracking-widest text-muted mb-2">{title}</div>
      {children}
    </div>
  );
}

function Bar({ label, value, color = "#22c55e", max = 1 }: { label: string; value: number; color?: string; max?: number }) {
  const pct = Math.max(0, Math.min(1, value / max)) * 100;
  return (
    <div className="flex items-center gap-2">
      <div className="text-[11px] text-muted w-40 truncate">{label}</div>
      <div className="flex-1 h-2 bg-bg rounded overflow-hidden">
        <div className="h-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="text-[11px] font-mono w-14 text-right" style={{ color }}>
        {value.toFixed(2)}
      </div>
    </div>
  );
}

function KV({ k, v, mono = true }: { k: string; v: React.ReactNode; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4 py-1 border-b border-line/40 last:border-0">
      <span className="text-[11px] text-muted">{k}</span>
      <span className={`text-[11px] text-white ${mono ? "font-mono" : ""}`}>{v}</span>
    </div>
  );
}

function Overview({
  detail,
  hovered,
  onHover,
  identity,
}: {
  detail: D;
  hovered?: string;
  onHover: (id?: string) => void;
  identity: "A" | "B";
}) {
  return (
    <div className="grid grid-cols-12 gap-3 h-full">
      <div className="col-span-3">
        <FaceZoneMap photo={detail.photo} zones={detail.zones} hovered={hovered} onHover={onHover} />
      </div>

      <div className="col-span-4 flex flex-col gap-3">
        <Panel title="Bayesian verdict">
          <Bar label="H0 — same person" value={detail.bayes.H0} color="#22c55e" />
          <div className="mt-1">
            <Bar label="H1 — double / mask" value={detail.bayes.H1} color="#ef4444" />
          </div>
          <div className="mt-1">
            <Bar label="H2 — different person" value={detail.bayes.H2} color="#f59e0b" />
          </div>
          <div className="text-[10px] text-muted mt-2">
            Identity cluster:{" "}
            <span className={identity === "A" ? "text-accent" : "text-danger"}>{identity}</span>
          </div>
        </Panel>
        <Panel title="Synthetic material detector">
          <Bar label="Synthetic probability" value={detail.texture.syntheticProb} color="#ef4444" />
          <div className="mt-1">
            <Bar label="FFT anomaly" value={detail.texture.fftAnomaly} color="#f59e0b" />
          </div>
          <div className="mt-1">
            <Bar label="Specular (shine)" value={detail.texture.specularIndex} color="#38bdf8" />
          </div>
          <div className="mt-1">
            <Bar label="Albedo health" value={detail.texture.albedoHealth} color="#22c55e" />
          </div>
        </Panel>
      </div>

      <div className="col-span-5 flex flex-col gap-3">
        <Panel title="Pose & expression">
          <div className="grid grid-cols-4 gap-2">
            <Stat label="yaw" value={`${detail.pose.yaw}°`} />
            <Stat label="pitch" value={`${detail.pose.pitch}°`} />
            <Stat label="roll" value={`${detail.pose.roll}°`} />
            <Stat label="conf." value={detail.pose.confidence.toFixed(2)} />
            <Stat label="class" value={detail.pose.classification} small />
            <Stat label="smile" value={detail.expression.smile.toFixed(2)} />
            <Stat label="jaw-open" value={detail.expression.jawOpen.toFixed(2)} />
            <Stat label="neutral" value={detail.expression.neutral ? "yes" : "no"} />
          </div>
          {detail.pose.fallback && (
            <div className="text-[10px] text-warn mt-2">
              ⓘ Primary pose detector low confidence — fell back to 3DDFA-V3.
            </div>
          )}
        </Panel>
        <Panel title="Chronology flags">
          <div className="text-[11px] space-y-1">
            <div className="text-muted">
              Δt = {detail.chronology.prevDelta}y · bone asymmetry jump:{" "}
              <span className="font-mono text-white">{detail.chronology.boneAsymmetryJump}</span> · ligament jump:{" "}
              <span className="font-mono text-white">{detail.chronology.ligamentJump}</span>
            </div>
            {detail.chronology.flags.length === 0 && (
              <div className="text-ok">No chronological inconsistencies detected.</div>
            )}
            {detail.chronology.flags.map((f, i) => (
              <div
                key={i}
                className={`${
                  f.severity === "danger" ? "text-danger" : f.severity === "warn" ? "text-warn" : "text-info"
                }`}
              >
                • {f.message}
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Notes">
          <ul className="text-[11px] text-muted space-y-1 list-disc list-inside">
            {detail.notes.map((n, i) => (
              <li key={i}>{n}</li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}

function Stat({ label, value, small = false }: { label: string; value: React.ReactNode; small?: boolean }) {
  return (
    <div className="bg-bg/60 rounded border border-line/60 p-2">
      <div className="text-[9px] uppercase text-muted tracking-wider">{label}</div>
      <div className={`font-mono ${small ? "text-[11px]" : "text-sm"} text-white`}>{value}</div>
    </div>
  );
}

function Reconstruction({ detail }: { detail: D }) {
  const layers = [
    { title: "Original", src: detail.photo },
    { title: "Face overlay", src: detail.reconstruction.overlay },
    { title: "Rendered face", src: detail.reconstruction.renderFace },
    { title: "Geometry (shape)", src: detail.reconstruction.renderShape },
    { title: "Mask", src: detail.reconstruction.renderMask },
    { title: "UV texture", src: detail.reconstruction.uvTexture },
    { title: "UV confidence", src: detail.reconstruction.uvConfidence },
    { title: "UV mask", src: detail.reconstruction.uvMask },
  ];
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-5 flex flex-col gap-3">
        <div className="bg-bg-deep rounded border border-line/60 overflow-hidden" style={{ height: 460 }}>
          <MeshViewer objUrl={detail.reconstruction.meshObj} />
        </div>
        <Panel title="Mesh statistics">
          <div className="grid grid-cols-2 gap-2">
            <Stat label="vertices" value={detail.reconstruction.vertices.toLocaleString()} />
            <Stat label="triangles" value={detail.reconstruction.meshTriangles.toLocaleString()} />
            <Stat label="model" value="3DDFA_v3" />
            <Stat label="neutral exp." value={detail.expression.neutral ? "yes" : "no"} />
          </div>
        </Panel>
      </div>
      <div className="col-span-7">
        <div className="grid grid-cols-3 gap-3">
          {layers.map((l) => (
            <div key={l.title} className="bg-bg-deep rounded border border-line/60 overflow-hidden">
              <img src={l.src} alt={l.title} className="w-full aspect-square object-contain bg-black" />
              <div className="px-2 py-1 text-[11px] text-white">{l.title}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SimilarTab({ photoId }: { photoId?: string }) {
  const [items, setItems] = useState<PhotoRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const { setPairA, setPairB, setPage } = useApp();

  useEffect(() => {
    if (!photoId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api.similarPhotos(photoId, 16).then((r) => {
      setItems(r);
      setLoading(false);
    });
  }, [photoId]);

  if (!photoId) {
    return (
      <div className="text-[11px] text-muted">
        Nearest-neighbour search is available when opening photos from the Photos page.
      </div>
    );
  }

  if (loading) return <div className="text-[11px] text-muted">Scoring {`>`} 1 700 photos…</div>;

  return (
    <div>
      <div className="text-[11px] text-muted mb-2">
        Top-{items.length} nearest photos by pose + cluster + synthetic profile.
      </div>
      <div className="grid grid-cols-8 gap-2">
        {items.map((p) => (
          <div
            key={p.id}
            className="bg-bg-deep rounded border border-line/60 overflow-hidden"
          >
            <img src={p.photo} alt="" className="w-full aspect-square object-cover" />
            <div className="px-1 py-1 text-[10px]">
              <div className="text-white font-mono truncate">{p.date}</div>
              <div className="text-muted">{p.pose}</div>
              <div className="flex gap-1 mt-1">
                <button
                  onClick={() => {
                    setPairA(photoId);
                    setPairB(p.id);
                    setPage("pairs");
                  }}
                  className="flex-1 px-1 py-0.5 rounded bg-accent/60 hover:bg-accent text-white text-[9px]"
                >
                  compare
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Zones({
  detail,
  hovered,
  onHover,
}: {
  detail: D;
  hovered?: string;
  onHover: (id?: string) => void;
}) {
  const grouped = {
    bone: detail.zones.filter((z) => z.group === "bone"),
    ligament: detail.zones.filter((z) => z.group === "ligament"),
    mixed: detail.zones.filter((z) => z.group === "mixed"),
    soft: detail.zones.filter((z) => z.group === "soft"),
  };
  const total = detail.zones.reduce((acc, z) => acc + z.weight, 0);
  const weighted = detail.zones.reduce((acc, z) => acc + z.weight * z.score, 0) / total;

  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-4">
        <FaceZoneMap photo={detail.photo} zones={detail.zones} hovered={hovered} onHover={onHover} />
        <Panel title="Aggregate" className="mt-3">
          <Bar label="Weighted similarity" value={weighted} color="#22c55e" />
          <div className="text-[10px] text-muted mt-2">
            Bone zones carry up to 1.00 weight; soft tissues are down-weighted or dynamically excluded (smile/jaw-open).
          </div>
        </Panel>
      </div>
      <div className="col-span-8 space-y-3">
        {(Object.entries(grouped) as [keyof typeof grouped, typeof detail.zones][]).map(([grp, zs]) => (
          <Panel key={grp} title={`${grp} zones (${zs.length})`}>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {zs.map((z) => (
                <div
                  key={z.id}
                  onMouseEnter={() => onHover(z.id)}
                  onMouseLeave={() => onHover(undefined)}
                  className={`flex items-center gap-2 px-1 rounded ${
                    hovered === z.id ? "bg-white/5" : ""
                  }`}
                >
                  <span className="text-[11px] text-white w-40 truncate">{z.name}</span>
                  <span
                    className={`text-[9px] px-1 rounded ${
                      z.priority === "max"
                        ? "bg-ok/30 text-ok"
                        : z.priority === "high"
                        ? "bg-info/30 text-info"
                        : z.priority === "medium"
                        ? "bg-warn/30 text-warn"
                        : "bg-muted/30 text-muted"
                    }`}
                  >
                    w {z.weight.toFixed(2)}
                  </span>
                  <div className="flex-1 h-1.5 bg-bg rounded">
                    <div
                      className="h-full rounded"
                      style={{
                        width: `${z.excluded ? 0 : z.score * 100}%`,
                        background: z.excluded ? "#6b7a90" : "#22c55e",
                      }}
                    />
                  </div>
                  {z.excluded && <span className="text-[9px] text-muted">excluded</span>}
                  {!z.visible && <span className="text-[9px] text-warn">hidden</span>}
                </div>
              ))}
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
}

function Texture({ detail }: { detail: D }) {
  // Seeded FFT radial histogram so the bars are stable across re-renders
  // and across audit runs.
  const r = rngFor("fft", detail.year, detail.photo);
  const bars = Array.from({ length: 24 }, (_, i) => {
    const anomaly = detail.texture.fftAnomaly;
    const base = Math.sin(i / 2) * 0.2 + 0.5;
    return Math.max(0.05, base + (r() - 0.5) * 0.2 + (i > 14 ? anomaly * 0.4 : 0));
  });
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-5 space-y-3">
        <Panel title="Synthetic probability breakdown">
          <Bar label="Synthetic probability" value={detail.texture.syntheticProb} color="#ef4444" />
          <div className="mt-1">
            <Bar label="FFT anomaly" value={detail.texture.fftAnomaly} color="#f59e0b" />
          </div>
          <div className="mt-1">
            <Bar label="LBP complexity" value={detail.texture.lbpComplexity} color="#a855f7" />
          </div>
          <div className="mt-1">
            <Bar label="Specular index" value={detail.texture.specularIndex} color="#38bdf8" />
          </div>
          <div className="mt-1">
            <Bar label="Albedo health" value={detail.texture.albedoHealth} color="#22c55e" />
          </div>
        </Panel>
        <Panel title="Diagnosis">
          <div className="text-[11px] text-muted leading-snug">
            {detail.texture.syntheticProb > 0.5
              ? "Texture pattern inconsistent with natural skin. Elevated FFT periodicity and specular index suggest possible silicone or latex prosthetic."
              : "Texture within natural-skin variability. No silicone/deepfake signatures detected."}
          </div>
        </Panel>
      </div>
      <div className="col-span-7 space-y-3">
        <Panel title="FFT spectrum (radial)">
          <div className="flex items-end h-32 gap-0.5">
            {bars.map((b, i) => (
              <div
                key={i}
                className="flex-1 bg-info/70"
                style={{ height: `${b * 100}%` }}
                title={`freq ${i}: ${b.toFixed(2)}`}
              />
            ))}
          </div>
          <div className="text-[10px] text-muted mt-2">
            Radial energy distribution over FFT of skin patches. Spikes in high frequencies indicate periodic patterns.
          </div>
        </Panel>
        <Panel title="UV texture vs confidence">
          <div className="grid grid-cols-2 gap-2">
            <img src={detail.reconstruction.uvTexture} alt="uv" className="w-full rounded bg-black" />
            <img src={detail.reconstruction.uvConfidence} alt="uv conf" className="w-full rounded bg-black" />
          </div>
        </Panel>
      </div>
    </div>
  );
}

function PoseAndExpression({ detail }: { detail: D }) {
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-6 space-y-3">
        <Panel title="Pose detector">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="yaw" value={`${detail.pose.yaw}°`} />
            <Stat label="pitch" value={`${detail.pose.pitch}°`} />
            <Stat label="roll" value={`${detail.pose.roll}°`} />
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Stat label="class" value={detail.pose.classification} small />
            <Stat label="confidence" value={detail.pose.confidence.toFixed(2)} />
            <Stat label="fallback" value={detail.pose.fallback ? "3DDFA-V3" : "primary"} small />
          </div>
        </Panel>
        <Panel title="Zone visibility (pose-gated)">
          <div className="grid grid-cols-2 gap-1 text-[11px]">
            {detail.zones.map((z) => (
              <div key={z.id} className="flex justify-between">
                <span className="text-muted">{z.name}</span>
                <span className={z.visible ? "text-ok" : "text-danger"}>{z.visible ? "visible" : "hidden"}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <div className="col-span-6 space-y-3">
        <Panel title="Expression">
          <Bar label="Smile" value={detail.expression.smile} color="#f59e0b" />
          <div className="mt-1">
            <Bar label="Jaw open" value={detail.expression.jawOpen} color="#f59e0b" />
          </div>
          <div className="text-[11px] text-muted mt-2">
            Thresholds: smile ≥ 0.30, jaw-open ≥ 0.25. Subject is{" "}
            <span className={detail.expression.neutral ? "text-ok" : "text-warn"}>
              {detail.expression.neutral ? "neutral" : "expressive"}
            </span>.
          </div>
        </Panel>
        <Panel title="Dynamically excluded zones">
          <div className="flex flex-wrap gap-1">
            {detail.expression.excludedZones.length === 0 && (
              <span className="text-[11px] text-ok">None — all zones participate.</span>
            )}
            {detail.expression.excludedZones.map((id) => (
              <span key={id} className="text-[10px] px-1.5 py-0.5 bg-muted/30 text-muted rounded">
                {id}
              </span>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function Chronology({ detail }: { detail: D }) {
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-5 space-y-3">
        <Panel title="Inter-frame deltas">
          <KV k="previous frame" v={detail.chronology.prevYear ?? "—"} />
          <KV k="Δt" v={`${detail.chronology.prevDelta} y`} />
          <KV k="bone asymmetry jump" v={detail.chronology.boneAsymmetryJump} />
          <KV k="ligament jump" v={detail.chronology.ligamentJump} />
        </Panel>
      </div>
      <div className="col-span-7">
        <Panel title="Raised flags">
          {detail.chronology.flags.length === 0 ? (
            <div className="text-[11px] text-ok">No chronological inconsistencies detected.</div>
          ) : (
            <ul className="space-y-1 text-[11px]">
              {detail.chronology.flags.map((f, i) => (
                <li
                  key={i}
                  className={
                    f.severity === "danger" ? "text-danger" : f.severity === "warn" ? "text-warn" : "text-info"
                  }
                >
                  • [{f.severity}] {f.message}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}

function CalibrationTab({ detail }: { detail: D }) {
  const c = detail.calibration;
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-6">
        <Panel title="Calibration bucket for this photo">
          <KV k="bucket" v={c.bucket} />
          <KV k="confidence level" v={c.level} />
          <KV k="sample count" v={c.sampleCount} />
          <KV k="variance" v={c.variance} />
        </Panel>
      </div>
      <div className="col-span-6">
        <Panel title="Runtime adaptation">
          <div className="text-[11px] text-muted leading-snug">
            {c.level === "high"
              ? "Direct strategy: standard thresholds applied."
              : c.level === "medium"
              ? "Conservative strategy: widened confidence intervals."
              : c.level === "low"
              ? "Low-confidence bucket — fallback weighted heavier towards bone-only comparison."
              : "Unreliable bucket — excluded from runtime comparisons until re-calibrated."}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function AuditTrailTab({ year, photoId }: { year: number; photoId?: string }) {
  const [items, setItems] = useState<LogEntry[]>([]);
  const [showAllLevels, setShowAllLevels] = useState(false);

  useEffect(() => {
    const filterAndSet = () => {
      const yearStr = String(year);
      const all = getAllLogs();
      setItems(
        all.filter((e) => {
          // Match if any of: log message contains year or photoId, or
          // payload (when serializable) contains either.
          const haystack = `${e.scope} ${e.message}`;
          if (haystack.includes(yearStr)) return true;
          if (photoId && haystack.includes(photoId)) return true;
          try {
            const json = JSON.stringify(e.data ?? "");
            if (json.includes(yearStr)) return true;
            if (photoId && json.includes(photoId)) return true;
          } catch {
            /* ignore */
          }
          return false;
        })
      );
    };
    filterAndSet();
    const unsub = subscribe(() => filterAndSet());
    return () => {
      unsub();
    };
  }, [year, photoId]);

  const visible = showAllLevels
    ? items
    : items.filter((e) => e.level !== "trace" && e.level !== "debug");

  const colorFor = (lvl: string) =>
    lvl === "error" ? "#ef4444" : lvl === "warn" ? "#f59e0b" : lvl === "info" ? "#22c55e" : "#6b7a90";

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[11px] text-muted">
          {visible.length} log entr{visible.length === 1 ? "y" : "ies"} touching{" "}
          <span className="text-white font-mono">year={year}</span>
          {photoId && (
            <>
              {" · "}
              <span className="text-white font-mono">photoId={photoId}</span>
            </>
          )}
        </div>
        <label className="flex items-center gap-2 text-[11px] text-white">
          <input
            type="checkbox"
            checked={showAllLevels}
            onChange={(e) => setShowAllLevels(e.target.checked)}
          />
          show trace/debug
        </label>
      </div>

      {visible.length === 0 ? (
        <div className="text-[11px] text-muted bg-bg-deep/50 border border-line/60 rounded p-3">
          No log entries reference this photo or year yet. Interact with it
          (open detail, change pair, run audit) to populate the trail.
        </div>
      ) : (
        <div className="font-mono text-[11px] bg-black/60 border border-line rounded">
          {visible.map((e) => (
            <details
              key={e.id}
              className={`border-b border-line/30 px-2 py-1 ${
                e.suspicious ? "bg-danger/10" : ""
              }`}
            >
              <summary className="cursor-pointer flex gap-2 items-baseline list-none">
                <span className="text-muted">
                  {new Date(e.ts).toISOString().slice(11, 23)}
                </span>
                <span style={{ color: colorFor(e.level) }} className="uppercase">
                  {e.level}
                </span>
                <span className="text-accent">{e.category}</span>
                <span className="text-info">{e.scope}</span>
                <span className="text-white flex-1 truncate">{e.message}</span>
                {e.durationMs !== undefined && (
                  <span className="text-muted">{e.durationMs}ms</span>
                )}
                {e.suspicious && <span className="text-danger">⚠{e.violations?.length}</span>}
              </summary>
              {e.violations && e.violations.length > 0 && (
                <div className="mt-1 space-y-1">
                  {e.violations.map((v, i) => (
                    <div
                      key={i}
                      className="px-2 py-1 rounded border border-danger/40 bg-danger/10"
                    >
                      <div className="text-danger">{v.field}</div>
                      <div className="text-muted">expected {v.expected}</div>
                      <div className="text-warn">actual {JSON.stringify(v.actual)}</div>
                      {v.note && <div className="italic text-muted">{v.note}</div>}
                    </div>
                  ))}
                </div>
              )}
              {e.data !== undefined && (
                <pre className="mt-1 text-muted whitespace-pre-wrap break-all text-[10px]">
                  {safeJson(e.data)}
                </pre>
              )}
            </details>
          ))}
        </div>
      )}
    </div>
  );
}

function safeJson(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function Meta({ detail }: { detail: D }) {
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-6">
        <Panel title="File">
          <KV k="photo id" v={detail.meta.id} />
          <KV k="filename" v={detail.meta.filename} />
          <KV k="captured at" v={detail.meta.capturedAt} />
          <KV k="source" v={detail.meta.source} />
          <KV k="resolution" v={detail.meta.resolution} />
          <KV k="size" v={`${detail.meta.sizeKB} KB`} />
          <KV k="md5" v={detail.meta.md5} />
        </Panel>
      </div>
      <div className="col-span-6">
        <Panel title="Pipeline cache">
          <KV k="reconstruction_v1.pkl" v="cached" />
          <KV k="neutral variant" v={detail.expression.neutral ? "present" : "needed"} />
          <KV k="VRAM footprint" v="~180 MB" />
          <KV k="last refreshed" v={`${detail.year}-01-01 · smoke-test`} />
        </Panel>
      </div>
    </div>
  );
}
