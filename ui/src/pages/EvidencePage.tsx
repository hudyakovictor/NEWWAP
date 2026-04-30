import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type EvidenceBreakdown } from "../api";
import { PHOTOS } from "../mock/photos";
import { useApp } from "../store/appStore";

export default function EvidencePage() {
  const { pairA, pairB, setPage } = useApp();
  const [ev, setEv] = useState<EvidenceBreakdown | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.getEvidence(pairA, pairB)
      .then((r) => {
        setEv(r);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message || "Failed to fetch evidence");
        setLoading(false);
      });
  }, [pairA, pairB]);

  const a = PHOTOS.find((p) => p.id === pairA)!;
  const b = PHOTOS.find((p) => p.id === pairB)!;

  return (
    <Page
      title="Evidence Synthesis"
      subtitle="Final forensic probability aggregation"
      actions={
        <button
          onClick={() => setPage("pairs")}
          className="px-4 h-9 rounded-full bg-white/10 hover:bg-white/20 transition-all text-[12px] font-medium text-white border border-white/10"
        >
          ← Back to Analysis
        </button>
      }
    >
      {loading ? (
        <div className="flex items-center gap-3 p-8 rounded-3xl bg-white/5 border border-line">
          <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin"></div>
          <div className="text-[12px] text-muted font-medium uppercase tracking-widest">Synthesizing forensic bundle...</div>
        </div>
      ) : error ? (
        <div className="p-6 bg-danger/10 border border-danger/20 rounded-3xl text-[12px] text-danger max-w-2xl shadow-xl shadow-danger/5">
          <div className="flex items-center gap-2 font-bold mb-3">
            <span className="w-2 h-2 rounded-full bg-danger animate-pulse"></span>
            PIPELINE_STALLED: DATA_MISSING
          </div>
          <p className="opacity-80 leading-relaxed mb-4">{error}</p>
          <div className="p-4 bg-black/40 rounded-2xl text-white/70 font-mono text-[11px]">
            This occurs when real forensic metrics for these specific IDs haven't been extracted. 
            Run the extraction job via the <span className="text-white underline cursor-pointer" onClick={() => setPage("photos")}>Dataset Inspector</span>.
          </div>
        </div>
      ) : !ev ? (
        <div className="text-[11px] text-muted p-8">Null result returned.</div>
      ) : (
        <div className="space-y-4">
          {/* Top Subjects */}
          <div className="grid grid-cols-2 gap-4">
            <SubjectMini label="SOURCE ALPHA" rec={a} side="L" />
            <SubjectMini label="SOURCE BETA" rec={b} side="R" />
          </div>

          <div className="grid grid-cols-12 gap-4">
            {/* Geometric */}
            <div className="col-span-12 lg:col-span-4 space-y-4">
              <PanelCard title="⚖️ Geometric Integrity" className="border-accent/20">
                <div className="space-y-4 py-2">
                  <IconStat label="Bone Structure SNR" value={ev.geometric.boneScore} icon="🦴" color="success" />
                  <IconStat label="Ligament Anchors" value={ev.geometric.ligamentScore} icon="⚓" color="info" />
                  <IconStat label="Soft-Tissue Delta" value={ev.geometric.softTissueScore} icon="🧬" color="warn" />
                  <div className="h-px bg-white/5 mt-2"></div>
                  <div className="flex justify-between items-center px-1">
                    <span className="text-[10px] text-muted uppercase font-bold tracking-tighter">Geometric SNR</span>
                    <span className="text-[12px] font-mono font-bold text-success">{(ev.geometric.snr * 10).toFixed(1)} dB</span>
                  </div>
                </div>
              </PanelCard>
              
              <PanelCard title="🕒 Chronology Status">
                <div className="flex items-center justify-between px-1 py-1">
                  <div className="text-[10px] text-muted uppercase font-bold tracking-tighter">Aging Period</div>
                  <div className="text-[12px] font-mono text-white">{ev.chronology.deltaYears} YRS</div>
                </div>
                <div className="mt-4 space-y-1">
                  {ev.chronology.flags.length === 0 ? (
                    <div className="text-[11px] text-success flex items-center gap-2 bg-success/10 p-2 rounded-xl border border-success/20">
                      <span className="text-lg">✓</span> Chronological sequence consistent
                    </div>
                  ) : (
                    ev.chronology.flags.map(f => (
                      <div key={f} className="text-[11px] text-warn flex items-center gap-2 bg-warn/10 p-2 rounded-xl border border-warn/20">
                        <span className="text-lg">⚠️</span> {f}
                      </div>
                    ))
                  )}
                </div>
              </PanelCard>
            </div>

            {/* Texture */}
            <div className="col-span-12 lg:col-span-4 space-y-4">
              <PanelCard title="🎭 Texture & Liveness" className="border-danger/20">
                <div className="space-y-4 py-2">
                  <IconStat label="Synthetic Match" value={ev.texture.syntheticProb} icon="🤖" color="danger" />
                  <IconStat label="FFT Periodicity" value={ev.texture.fft} icon="〰️" color="warn" />
                  <IconStat label="LBP Complexity" value={ev.texture.lbp} icon="🕸️" color="info" />
                  <IconStat label="Albedo Viability" value={ev.texture.albedo} icon="💡" color="success" />
                </div>
              </PanelCard>

              <PanelCard title="📐 Pose Gating">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 rounded-2xl bg-bg-deep border border-line">
                    <div className="text-[9px] text-muted uppercase font-bold tracking-widest mb-1 text-center">Visibility</div>
                    <div className="text-lg font-mono font-bold text-info text-center">{ev.pose.mutualVisibility}<span className="text-[10px] opacity-40 ml-1">/21</span></div>
                  </div>
                  <div className="p-3 rounded-2xl bg-bg-deep border border-line">
                    <div className="text-[9px] text-muted uppercase font-bold tracking-widest mb-1 text-center">Excluded</div>
                    <div className="text-lg font-mono font-bold text-muted text-center">{ev.pose.expressionExcluded}</div>
                  </div>
                </div>
              </PanelCard>
            </div>

            {/* Verdict */}
            <div className="col-span-12 lg:col-span-4">
              <PanelCard title="👨‍⚖️ Final Verdict" className="h-full bg-accent/5 border-accent/30 shadow-2xl shadow-accent/5">
                <div className="flex flex-col h-full">
                  <div className="text-center py-6 mb-4 rounded-3xl bg-bg-deep/80 border border-accent/20">
                    <div className="text-[10px] text-muted uppercase font-black tracking-[0.3em] mb-2">Likely Conclusion</div>
                    <div className={`text-xl font-black uppercase tracking-wider ${ev.verdict.includes('Substitution') ? 'text-danger' : 'text-success'}`}>
                      {ev.verdict.split('—')[0]}
                    </div>
                  </div>

                  <div className="space-y-3 flex-1">
                    <VerdictRow label="H0: Same Identity" value={ev.posteriors.H0} color="success" />
                    <VerdictRow label="H1: Mask / Double" value={ev.posteriors.H1} color="danger" />
                    <VerdictRow label="H2: Different Subject" value={ev.posteriors.H2} color="warn" />
                  </div>

                  <div className="mt-8 p-4 rounded-2xl bg-white/5 border border-white/10 italic text-[11px] text-white/60 leading-relaxed">
                    "Geometric similarity across {ev.pose.mutualVisibility} mutually visible zones suggests {ev.verdict.toLowerCase()}."
                  </div>
                </div>
              </PanelCard>
            </div>
          </div>

          {/* Details */}
          <details className="group mt-8">
            <summary className="list-none flex items-center gap-2 cursor-pointer text-[11px] font-bold text-muted uppercase tracking-widest hover:text-white transition-colors bg-white/5 w-fit px-4 py-2 rounded-full border border-white/5">
              <span className="group-open:rotate-180 transition-transform">▼</span> RAW FORENSIC BUNDLE (JSON)
            </summary>
            <div className="mt-4 p-4 rounded-3xl bg-black/60 border border-line overflow-auto max-h-96 custom-scrollbar shadow-inner">
              <pre className="text-[10px] font-mono text-info/80 leading-relaxed">
                {JSON.stringify(ev, null, 2)}
              </pre>
            </div>
          </details>
        </div>
      )}
    </Page>
  );
}

function SubjectMini({ label, rec, side }: { label: string; rec: any; side: string }) {
  return (
    <div className={`flex items-center gap-4 p-4 rounded-3xl bg-bg-deep/40 border border-line backdrop-blur-md shadow-lg ${side === 'L' ? 'flex-row' : 'flex-row-reverse'}`}>
      <div className="relative group">
        <img src={rec.photo} className="w-20 h-20 object-cover rounded-2xl border-2 border-line group-hover:border-accent transition-all duration-500 shadow-lg" alt="" />
        <div className={`absolute -top-2 ${side === 'L' ? '-left-2' : '-right-2'} w-6 h-6 rounded-full bg-accent border-2 border-bg-deep flex items-center justify-center text-[10px] font-black`}>
          {side}
        </div>
      </div>
      <div className={`flex-1 ${side === 'R' ? 'text-right' : ''}`}>
        <div className="text-[10px] text-muted font-black tracking-widest mb-1">{label}</div>
        <div className="text-[13px] font-bold text-white mb-0.5">{rec.id.split('-').slice(1,3).join(' ')}</div>
        <div className="text-[10px] font-mono text-info uppercase">{rec.date} · {rec.pose}</div>
      </div>
    </div>
  );
}

function IconStat({ label, value, icon, color }: { label: string; value: number; icon: string; color: string }) {
  const colorMap: any = {
    success: 'bg-success shadow-success/40',
    danger: 'bg-danger shadow-danger/40',
    warn: 'bg-warn shadow-warn/40',
    info: 'bg-info shadow-info/40'
  };
  
  return (
    <div className="group">
      <div className="flex justify-between items-center mb-1.5 px-1">
        <div className="flex items-center gap-2">
          <span className="text-sm grayscale group-hover:grayscale-0 transition-all duration-300">{icon}</span>
          <span className="text-[10px] font-bold text-muted uppercase tracking-tighter group-hover:text-white/80 transition-colors">{label}</span>
        </div>
        <span className="text-[11px] font-mono font-bold text-white/90">{(value * 100).toFixed(0)}<span className="opacity-40 text-[9px] ml-0.5">%</span></span>
      </div>
      <div className="h-1.5 w-full bg-bg-deep rounded-full overflow-hidden border border-white/5">
        <div 
          className={`h-full rounded-full transition-all duration-1000 ease-out shadow-[0_0_8px] ${colorMap[color]}`}
          style={{ width: `${value * 100}%` }}
        />
      </div>
    </div>
  );
}

function VerdictRow({ label, value, color }: { label: string; value: number; color: string }) {
  const colorText: any = { success: 'text-success', danger: 'text-danger', warn: 'text-warn' };
  const colorBg: any = { success: 'bg-success', danger: 'bg-danger', warn: 'bg-warn' };

  return (
    <div className="space-y-1.5 p-3 rounded-2xl bg-white/5 border border-white/5 hover:bg-white/10 transition-colors">
      <div className="flex justify-between items-center">
        <span className="text-[10px] font-bold text-muted uppercase tracking-tight">{label}</span>
        <span className={`text-[12px] font-mono font-black ${colorText[color]}`}>{(value * 100).toFixed(1)}%</span>
      </div>
      <div className="h-1.5 w-full bg-bg-deep rounded-full overflow-hidden">
        <div 
          className={`h-full rounded-full ${colorBg[color]} transition-all duration-1000 ease-out`}
          style={{ width: `${value * 100}%` }}
        />
      </div>
    </div>
  );
}
