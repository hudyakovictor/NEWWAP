import { useMemo, useState, useEffect } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { PHOTOS, type PhotoRecord } from "../mock/photos";
import { FACE_ZONES } from "../mock/photoDetail";
import { useApp } from "../store/appStore";
import { api, type EvidenceBreakdown } from "../api";
import { ALL_PHOTOS } from "../data/photoRegistry";
import { getBucketFallbackPolicy, buildCalibrationHealth, type CalibrationHealth } from "../data/calibrationBuckets";

/** Lookup the real pose record for a photo id. Returns null if unknown. */
function realPose(id: string) {
  const r = ALL_PHOTOS.find((p) => p.id === id);
  return r?.pose ?? null;
}

/** Side-aware zone visibility from real yaw.
 *  Convention: positive yaw = subject looks to the right, exposing more of
 *  the LEFT side of the face to the camera (mirror-like). Zones suffixed
 *  `_r` hide when yaw is sufficiently negative (right side of the face is
 *  occluded), `_l` hide when yaw is sufficiently positive. */
function zoneVisibleFromYaw(zoneId: string, yawDeg: number | null): boolean {
  if (yawDeg == null) return true; // unknown pose → assume visible
  if (zoneId.endsWith("_r")) return yawDeg > -55;
  if (zoneId.endsWith("_l")) return yawDeg < 55;
  return true;
}

export default function PairAnalysisPage() {
  const { pairA, pairB, setPairA, setPairB } = useApp();
  const a = PHOTOS.find((p) => p.id === pairA) ?? PHOTOS[0];
  const b = PHOTOS.find((p) => p.id === pairB) ?? PHOTOS[1];
  
  const [calibrationHealth, setCalibrationHealth] = useState<CalibrationHealth | null>(null);
  const [ev, setEv] = useState<EvidenceBreakdown | null>(null);
  
  useEffect(() => {
    setCalibrationHealth(buildCalibrationHealth());
  }, []);

  useEffect(() => {
    setEv(null);
    api.getEvidence(pairA, pairB).then(setEv).catch(console.error);
  }, [pairA, pairB]);

  const realA = realPose(a.id);
  const realB = realPose(b.id);
  
  // Calibration context for this pair
  const calibrationContext = useMemo(() => {
    if (!realA || !realB) return null;
    // Use photo A's classification and estimated light for bucket lookup
    const pose = realA.classification ?? "unknown";
    const light = "daylight"; // Simplified - would come from face_stats
    const policy = getBucketFallbackPolicy(pose, light);
    
    return {
      poseA: realA.classification,
      poseB: realB.classification,
      deltaYaw: realA.yaw != null && realB.yaw != null ? Math.abs(realA.yaw - realB.yaw) : null,
      bucketKey: `${pose}_${light}`,
      ...policy,
    };
  }, [realA, realB]);

  // Real Δpose (when both photos have a real pose entry)
  const deltaPose = realA && realB
    ? {
        yaw: +(((realA.yaw ?? 0) - (realB.yaw ?? 0))).toFixed(1),
        pitch: +(((realA.pitch ?? 0) - (realB.pitch ?? 0))).toFixed(1),
        roll: +(((realA.roll ?? 0) - (realB.roll ?? 0))).toFixed(1),
      }
    : null;

  // Visibility now driven by REAL yaw of each subject.
  const zoneComparison = useMemo(() => {
    return FACE_ZONES.map((z, i) => {
      const visibleA = zoneVisibleFromYaw(z.id, realA?.yaw ?? null);
      const visibleB = zoneVisibleFromYaw(z.id, realB?.yaw ?? null);
      const both = visibleA && visibleB;
      const smileAffected = ["lip_upper", "lip_lower", "nose_wing_l", "nose_wing_r", "cheek_l", "cheek_r"].includes(z.id);
      const excluded = smileAffected && (a.expression === "smile" || b.expression === "smile");
      let score = 0;
      if (both && !excluded) {
        const base = z.group === "bone" ? 0.82 : z.group === "ligament" ? 0.7 : 0.55;
        const penalty = a.cluster !== b.cluster ? 0.25 : 0;
        const r = ((i * 37 + a.year + b.year) % 100) / 1000;
        score = Math.max(0, Math.min(1, base - penalty + r));
      }
      return { ...z, visibleA, visibleB, both, excluded, scoreAB: score };
    });
  }, [a, b]);

  return (
    <Page
      title="Pair analysis"
      subtitle="Side-by-side forensic comparison with bayesian courtroom verdict"
      actions={
        <button className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">
          Save case
        </button>
      }
    >
      {calibrationContext && !calibrationContext.ready && (
        <div className="mb-3 p-2 rounded bg-warn/20 border border-warn/40 text-[11px]">
          <strong>⚠️ Calibration fallback active:</strong> Bucket "{calibrationContext.bucketKey}" has 
          {calibrationContext.mode === "strict" ? " insufficient samples" : " low confidence"}. 
          Using {calibrationContext.mode} scoring mode (confidence: {(calibrationContext.confidence * 100).toFixed(0)}%).
        </div>
      )}
      
      <div className="grid grid-cols-2 gap-3 mb-3">
        <PhotoSlot label="Photo A" photo={a} onPick={setPairA} />
        <PhotoSlot label="Photo B" photo={b} onPick={setPairB} />
      </div>

      <PanelCard title="Pose comparison (real)" className="mb-3">
        {!realA || !realB ? (
          <div className="text-[11px] text-muted">
            Real pose missing for {!realA ? "A" : !realB ? "B" : "?"}; mutual visibility falls back to "assume visible".
          </div>
        ) : (
          <div className="grid grid-cols-7 gap-2 text-[11px]">
            <PoseCell label="A pose"      val={`${realA.classification} (${realA.source})`} mono={false} />
            <PoseCell label="A yaw"       val={`${realA.yaw?.toFixed(1)}°`} />
            <PoseCell label="A pitch"     val={`${realA.pitch?.toFixed(1)}°`} />
            <PoseCell label="B pose"      val={`${realB.classification} (${realB.source})`} mono={false} />
            <PoseCell label="B yaw"       val={`${realB.yaw?.toFixed(1)}°`} />
            <PoseCell label="B pitch"     val={`${realB.pitch?.toFixed(1)}°`} />
            <PoseCell
              label="Δyaw"
              val={deltaPose ? `${deltaPose.yaw}°` : "—"}
              color={deltaPose && Math.abs(deltaPose.yaw) > 30 ? "#f59e0b" : "#22c55e"}
            />
          </div>
        )}
      </PanelCard>

      <div className="grid grid-cols-3 gap-3">
        <PanelCard title="Evidence synthesis">
          {!ev ? <div className="text-[11px] text-muted py-4">Fetching real evidence...</div> : (
            <>
              <StatBar label="Geometric similarity" value={ev.geometric.boneScore} color="#22c55e" />
              <StatBar label="SNR (bone vs noise)" value={Math.min(1, ev.geometric.snr / 10)} color="#38bdf8" rawText={ev.geometric.snr.toFixed(1) + " dB"} />
              <StatBar label="Silicone prob. (max)" value={ev.texture.syntheticProb} color="#ef4444" />
              <StatBar
                label="Chronological delta (y)"
                value={Math.min(1, ev.chronology.deltaYears / 30)}
                color="#f59e0b"
                rawText={String(ev.chronology.deltaYears)}
              />
            </>
          )}
        </PanelCard>

        <PanelCard title="Bayesian courtroom">
          {!ev ? <div className="text-[11px] text-muted py-4">Computing posteriors...</div> : (
            <>
              <StatBar label="H0 · same person" value={ev.posteriors.H0} color="#22c55e" />
              <StatBar label="H1 · double / mask" value={ev.posteriors.H1} color="#ef4444" />
              <StatBar label="H2 · different people" value={ev.posteriors.H2} color="#f59e0b" />
              <div className="text-[11px] text-muted mt-2 leading-snug font-semibold text-white">
                Verdict: {ev.verdict}
              </div>
            </>
          )}
        </PanelCard>

        <PanelCard title="Pose compatibility">
          <KV k="A pose" v={a.pose} />
          <KV k="B pose" v={b.pose} />
          <KV
            k="mutual visibility"
            v={`${zoneComparison.filter((z) => z.both && !z.excluded).length} / ${zoneComparison.length} zones`}
          />
          <KV k="expression-driven exclusions" v={zoneComparison.filter((z) => z.excluded).length} />
          {calibrationHealth && (
            <>
              <KV 
                k="calibration buckets" 
                v={`${calibrationHealth.usableBucketCount}/${calibrationHealth.bucketCount} ready`} 
              />
              <KV 
                k="trusted buckets" 
                v={calibrationHealth.trustedBucketCount} 
              />
            </>
          )}
          <div className="text-[11px] text-muted mt-2">
            Hidden/excluded zones are removed from similarity calculation to avoid pose-induced false negatives.
          </div>
        </PanelCard>
      </div>

      <PanelCard title="21-zone comparison" className="mt-3">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {zoneComparison.map((z) => (
            <div key={z.id} className="flex items-center gap-2">
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
                    width: `${z.scoreAB * 100}%`,
                    background: z.excluded || !z.both ? "#6b7a90" : "#22c55e",
                  }}
                />
              </div>
              {!z.both && <span className="text-[9px] text-warn">hidden</span>}
              {z.excluded && <span className="text-[9px] text-muted">excluded</span>}
            </div>
          ))}
        </div>
      </PanelCard>
    </Page>
  );
}

function PhotoSlot({
  label,
  photo,
  onPick,
}: {
  label: string;
  photo: PhotoRecord;
  onPick: (id: string) => void;
}) {
  const [q, setQ] = useState("");
  const candidates = PHOTOS.filter((p) => !q || p.date.includes(q) || p.id.includes(q)).slice(0, 12);

  return (
    <PanelCard title={label}>
      <div className="flex gap-3">
        <img src={photo.photo} alt="" className="w-32 h-32 rounded object-cover border border-line" />
        <div className="flex-1">
          <div className="text-sm text-white font-semibold">{photo.id}</div>
          <div className="text-[11px] text-muted">{photo.date} · {photo.pose} · {photo.expression}</div>
          <div className="text-[11px] mt-1 flex flex-wrap gap-1">
            {photo.flags.map((f) => (
              <span key={f} className="px-1 rounded bg-warn/30 text-warn text-[9px]">{f}</span>
            ))}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1 text-[11px]">
            <KV k="cluster" v={photo.cluster} />
            <KV k="synthetic" v={photo.syntheticProb.toFixed(2)} />
          </div>
        </div>
      </div>
      <div className="mt-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="filter id / date"
          className="w-full h-7 px-2 rounded bg-bg-deep border border-line text-[11px] text-white"
        />
        <div className="grid grid-cols-6 gap-1 mt-2">
          {candidates.map((p) => (
            <button
              key={p.id}
              onClick={() => onPick(p.id)}
              className={`rounded overflow-hidden border ${p.id === photo.id ? "border-ok" : "border-line hover:border-info"}`}
              title={p.id}
            >
              <img src={p.photo} alt="" className="w-full aspect-square object-cover" />
            </button>
          ))}
        </div>
      </div>
    </PanelCard>
  );
}

function PoseCell({
  label,
  val,
  color = "#cfd8e6",
  mono = true,
}: {
  label: string;
  val: React.ReactNode;
  color?: string;
  mono?: boolean;
}) {
  return (
    <div className="bg-bg-deep/70 border border-line/60 rounded p-2">
      <div className="text-[9px] uppercase tracking-widest text-muted">{label}</div>
      <div className={`${mono ? "font-mono" : ""} text-sm`} style={{ color }}>
        {val}
      </div>
    </div>
  );
}

function StatBar({
  label,
  value,
  color,
  rawText,
}: {
  label: string;
  value: number;
  color: string;
  rawText?: string;
}) {
  return (
    <div className="flex items-center gap-2 my-1">
      <div className="text-[11px] text-muted w-44 truncate">{label}</div>
      <div className="flex-1 h-2 bg-bg rounded overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, value * 100)}%`, background: color }} />
      </div>
      <div className="text-[11px] font-mono w-14 text-right" style={{ color }}>
        {rawText ?? value.toFixed(2)}
      </div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between text-[11px] border-b border-line/40 py-0.5">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-white">{v}</span>
    </div>
  );
}
