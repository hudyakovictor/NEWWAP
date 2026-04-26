import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type EvidenceBreakdown } from "../api";
import { PHOTOS } from "../mock/photos";
import { useApp } from "../store/appStore";
import StubBanner from "../components/common/StubBanner";

export default function EvidencePage() {
  const { pairA, pairB, setPage } = useApp();
  const [ev, setEv] = useState<EvidenceBreakdown | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.getEvidence(pairA, pairB).then((r) => {
      setEv(r);
      setLoading(false);
    });
  }, [pairA, pairB]);

  const a = PHOTOS.find((p) => p.id === pairA)!;
  const b = PHOTOS.find((p) => p.id === pairB)!;

  return (
    <Page
      title="Evidence synthesis (debug)"
      subtitle="Full bayesian courtroom breakdown for current Pair A / B"
      actions={
        <button
          onClick={() => setPage("pairs")}
          className="px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white"
        >
          ← Pair analysis
        </button>
      }
    >
      {loading || !ev ? (
        <div className="text-[11px] text-muted">Synthesizing evidence…</div>
      ) : (
        <div className="space-y-3">
          {/* Header */}
          <div className="grid grid-cols-2 gap-3">
            <SubjectCard label="Photo A" rec={a} />
            <SubjectCard label="Photo B" rec={b} />
          </div>

          {/* Evidence sources */}
          <div className="grid grid-cols-12 gap-3">
            <PanelCard title="1. Geometric evidence (bone structures)" className="col-span-6">
              <Bar label="SNR (signal/noise)"      value={ev.geometric.snr}               color="#22c55e" />
              <Bar label="Bone zones score"         value={ev.geometric.boneScore}         color="#22c55e" />
              <Bar label="Ligament anchors score"   value={ev.geometric.ligamentScore}     color="#38bdf8" />
              <Bar label="Soft-tissue residual"     value={ev.geometric.softTissueScore}   color="#a855f7" />
              <div className="text-[11px] text-muted mt-2">
                Bone score dominates with weight up to 1.00; ligament anchors checked for pose visibility; soft-tissue is downweighted & excluded on smile.
              </div>
            </PanelCard>

            <PanelCard title="2. Texture evidence (synthetic material)" className="col-span-6">
              <Bar label="Synthetic probability (combined)" value={ev.texture.syntheticProb}  color="#ef4444" />
              <Bar label="FFT periodicity anomaly"          value={ev.texture.fft}            color="#f59e0b" />
              <Bar label="LBP texture complexity"           value={ev.texture.lbp}            color="#a855f7" />
              <Bar label="Albedo skin viability"            value={ev.texture.albedo}         color="#22c55e" />
              <Bar label="Specular (shine) index"           value={ev.texture.specular}       color="#38bdf8" />
            </PanelCard>

            <PanelCard title="3. Chronology evidence" className="col-span-6">
              <div className="grid grid-cols-3 gap-2">
                <KV k="Δt (years)"       v={ev.chronology.deltaYears} />
                <KV k="bone jump"        v={ev.chronology.boneJump} />
                <KV k="ligament jump"    v={ev.chronology.ligamentJump} />
              </div>
              <div className="mt-2">
                <div className="text-[10px] uppercase tracking-widest text-muted mb-1">Flags</div>
                {ev.chronology.flags.length === 0 ? (
                  <div className="text-[11px] text-ok">No chronological inconsistencies.</div>
                ) : (
                  <ul className="text-[11px] text-warn space-y-0.5">
                    {ev.chronology.flags.map((f) => <li key={f}>• {f}</li>)}
                  </ul>
                )}
              </div>
            </PanelCard>

            <PanelCard title="4. Pose & expression gating" className="col-span-6">
              <div className="grid grid-cols-2 gap-2">
                <KV k="mutual zone visibility" v={`${ev.pose.mutualVisibility}/21`} />
                <KV k="expression-excluded" v={ev.pose.expressionExcluded} />
              </div>
              <div className="text-[11px] text-muted mt-2">
                Only mutually visible + not-excluded zones contribute to the weighted similarity used in the geometric likelihood.
              </div>
            </PanelCard>
          </div>

          {/* Bayesian math */}
          <PanelCard title="5. Bayesian update">
            <table className="w-full text-[11px]">
              <thead className="text-muted border-b border-line">
                <tr>
                  <th className="text-left p-2">hypothesis</th>
                  <th className="text-left p-2">prior P(H)</th>
                  <th className="text-left p-2">likelihood P(E|H)</th>
                  <th className="text-left p-2">prior × like</th>
                  <th className="text-left p-2">posterior P(H|E)</th>
                </tr>
              </thead>
              <tbody>
                {(["H0", "H1", "H2"] as const).map((h) => {
                  const pri = ev.priors[h];
                  const lik = ev.likelihoods[h];
                  const post = ev.posteriors[h];
                  const color = h === "H0" ? "#22c55e" : h === "H1" ? "#ef4444" : "#f59e0b";
                  return (
                    <tr key={h} className="border-b border-line/40">
                      <td className="p-2 font-semibold" style={{ color }}>{h}</td>
                      <td className="p-2 font-mono text-white">{pri.toFixed(3)}</td>
                      <td className="p-2 font-mono text-white">{lik.toFixed(3)}</td>
                      <td className="p-2 font-mono text-muted">{(pri * lik).toFixed(4)}</td>
                      <td className="p-2">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-bg rounded overflow-hidden">
                            <div className="h-full" style={{ width: `${post * 100}%`, background: color }} />
                          </div>
                          <span className="font-mono w-12 text-right" style={{ color }}>
                            {(post * 100).toFixed(1)}%
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="text-[11px] text-muted mt-2">
              Normalization constant Z = Σ prior × likelihood.
              Verdict = argmax posterior → <span className="text-white font-semibold">{ev.verdict}</span>.
            </div>
          </PanelCard>

          <PanelCard title="6. Raw JSON">
            <pre className="text-[10px] bg-black/60 border border-line p-2 rounded overflow-auto max-h-64 text-muted">
              {JSON.stringify(ev, null, 2)}
            </pre>
          </PanelCard>
        </div>
      )}
    </Page>
  );
}

function SubjectCard({ label, rec }: { label: string; rec: (typeof PHOTOS)[number] }) {
  return (
    <PanelCard title={label}>
      <div className="flex gap-3">
        <img src={rec.photo} alt="" className="w-20 h-20 object-cover rounded border border-line" />
        <div className="flex-1 text-[11px]">
          <div className="text-white font-mono">{rec.id}</div>
          <div className="text-muted">{rec.date} · {rec.pose} · {rec.expression}</div>
          <div className="mt-1 flex flex-wrap gap-1">
            {rec.flags.map((f) => (
              <span key={f} className="text-[9px] px-1 rounded bg-warn/30 text-warn">{f}</span>
            ))}
          </div>
          <div className="mt-1 grid grid-cols-2 gap-1">
            <KV k="cluster" v={rec.cluster} />
            <KV k="synthetic" v={rec.syntheticProb.toFixed(2)} />
          </div>
        </div>
      </div>
    </PanelCard>
  );
}

function Bar({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-2 my-1">
      <div className="text-[11px] text-muted w-56 truncate">{label}</div>
      <div className="flex-1 h-2 bg-bg rounded overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, value * 100)}%`, background: color }} />
      </div>
      <div className="text-[11px] font-mono w-14 text-right" style={{ color }}>{value.toFixed(3)}</div>
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
