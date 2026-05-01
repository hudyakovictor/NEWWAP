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
          {/* [FIX-18] Data Quality Warning Banner */}
          {ev.dataQuality && ev.dataQuality.coverageRatio < 0.5 && (
            <div className="p-4 rounded-2xl bg-warn/10 border border-warn/30 mb-4">
              <div className="flex items-center gap-3">
                <span className="text-2xl">⚠️</span>
                <div>
                  <div className="text-[12px] font-bold text-warn uppercase tracking-wider">INSUFFICIENT DATA COVERAGE</div>
                  <div className="text-[11px] text-white/70">
                    Only {(ev.dataQuality.coverageRatio * 100).toFixed(0)}% of required zones available. 
                    Verdict confidence is reduced.
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Top Subjects */}
          <div className="grid grid-cols-2 gap-4">
            <SubjectMini label="SOURCE ALPHA" rec={a} side="L" />
            <SubjectMini label="SOURCE BETA" rec={b} side="R" />
          </div>

          <div className="grid grid-cols-12 gap-4">
            {/* [FIX-18] Data Quality & Zone Coverage */}
            <div className="col-span-12 lg:col-span-3 space-y-4">
              <PanelCard title="📊 Data Quality" className="border-warn/20">
                <div className="space-y-3 py-2">
                  <QualityStat 
                    label="Zone Coverage" 
                    value={ev.dataQuality?.coverageRatio ?? 0.5} 
                    target={0.8}
                    suffix="%"
                  />
                  <QualityStat 
                    label="Zones Analyzed" 
                    value={ev.geometric?.zoneCount ?? 0} 
                    target={21}
                    suffix="/21"
                    raw
                  />
                  
                  {ev.geometric?.excludedZones && ev.geometric.excludedZones.length > 0 && (
                    <div className="mt-3 p-2 rounded-xl bg-warn/10 border border-warn/20">
                      <div className="text-[9px] text-warn uppercase font-bold tracking-wider mb-1">
                        Excluded ({ev.pose?.expressionExcluded ?? 0})
                      </div>
                      <div className="text-[10px] text-white/70 leading-tight">
                        {ev.geometric.excludedZones.slice(0, 3).join(', ')}
                        {ev.geometric.excludedZones.length > 3 && ` +${ev.geometric.excludedZones.length - 3} more`}
                      </div>
                    </div>
                  )}
                  
                  {ev.methodologyVersion && (
                    <div className="mt-2 text-[9px] text-muted font-mono">
                      Method: {ev.methodologyVersion}
                    </div>
                  )}
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

            {/* [FIX-18] Geometric with Zone Divergence */}
            <div className="col-span-12 lg:col-span-3 space-y-4">
              <PanelCard title="⚖️ Geometric Integrity" className="border-accent/20">
                <div className="space-y-4 py-2">
                  <IconStat label="Bone Structure SNR" value={ev.geometric.boneScore} icon="🦴" color="success" />
                  <IconStat label="Ligament Anchors" value={ev.geometric.ligamentScore} icon="⚓" color="info" />
                  <IconStat label="Soft-Tissue Delta" value={ev.geometric.softTissueScore} icon="🧬" color="warn" />
                  <div className="h-px bg-white/5 mt-2"></div>
                  <div className="flex justify-between items-center px-1">
                    <span className="text-[10px] text-muted uppercase font-bold tracking-tighter">Geometric SNR</span>
                    <span className="text-[12px] font-mono font-bold text-success">{ev.geometric.snr.toFixed(1)} dB</span>
                  </div>
                  
                  {ev.geometric?.categoryDivergence && (
                    <div className="mt-3 space-y-1">
                      <div className="text-[9px] text-muted uppercase font-bold">Category Divergence</div>
                      {Object.entries(ev.geometric.categoryDivergence).slice(0, 3).map(([cat, val]) => (
                        <div key={cat} className="flex justify-between text-[10px]">
                          <span className="text-white/60">{cat}</span>
                          <span className="font-mono">{(val as number).toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </PanelCard>
            </div>

            {/* [FIX-18] Texture with Raw/Adjusted split */}
            <div className="col-span-12 lg:col-span-3 space-y-4">
              <PanelCard title="🎭 Texture Analysis" className="border-danger/20">
                <div className="space-y-4 py-2">
                  {/* Synthetic Probability with Raw/Adjusted */}
                  <div className="space-y-1">
                    <div className="flex justify-between items-center px-1">
                      <div className="flex items-center gap-2">
                        <span className="text-sm">🤖</span>
                        <span className="text-[10px] font-bold text-muted uppercase tracking-tighter">Synthetic Probability</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 px-1">
                      <div className="flex-1 h-2 bg-bg-deep rounded-full overflow-hidden">
                        <div className="h-full bg-danger rounded-full" style={{ width: `${(ev.texture.syntheticProb ?? 0) * 100}%` }} />
                      </div>
                      <span className="text-[11px] font-mono font-bold text-danger">
                        {((ev.texture.syntheticProb ?? 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                    {(ev.texture.rawSyntheticProb !== undefined || ev.texture.naturalScore !== undefined) && (
                      <div className="flex justify-between text-[9px] text-muted px-1">
                        {ev.texture.rawSyntheticProb !== undefined && (
                          <span>raw: {(ev.texture.rawSyntheticProb * 100).toFixed(0)}%</span>
                        )}
                        {ev.texture.naturalScore !== undefined && (
                          <span className="text-success">natural: {(ev.texture.naturalScore * 100).toFixed(0)}%</span>
                        )}
                      </div>
                    )}
                  </div>
                  
                  <IconStat label="FFT Periodicity" value={ev.texture.fft} icon="〰️" color="warn" />
                  <IconStat label="LBP Complexity" value={ev.texture.lbp} icon="🕸️" color="info" />
                  <IconStat label="Albedo Uniformity" value={ev.texture.albedo} icon="💡" color="success" />
                  
                  {/* [FIX-19] H1 Subtype Classification */}
                  {ev.texture.h1Subtype && ev.texture.syntheticProb > 0.3 && (
                    <div className="mt-3 p-2 rounded-xl bg-danger/10 border border-danger/20">
                      <div className="text-[9px] text-danger uppercase font-bold tracking-wider mb-1">
                        Detected Type (H1)
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-lg">
                          {ev.texture.h1Subtype.primary === 'mask' ? '🎭' :
                           ev.texture.h1Subtype.primary === 'deepfake' ? '🤖' :
                           ev.texture.h1Subtype.primary === 'prosthetic' ? '🔧' : '❓'}
                        </span>
                        <div>
                          <div className="text-[12px] font-bold text-white capitalize">
                            {ev.texture.h1Subtype.primary}
                          </div>
                          <div className="text-[9px] text-white/60">
                            confidence: {(ev.texture.h1Subtype.confidence * 100).toFixed(0)}%
                          </div>
                        </div>
                      </div>
                      {ev.texture.h1Subtype.indicators.length > 0 && (
                        <div className="mt-1 text-[9px] text-white/50">
                          {ev.texture.h1Subtype.indicators.slice(0, 2).join(', ')}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </PanelCard>

              <PanelCard title="📐 Pose & Gating">
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-3 rounded-2xl bg-bg-deep border border-line">
                    <div className="text-[9px] text-muted uppercase font-bold tracking-widest mb-1 text-center">Visibility</div>
                    <div className="text-lg font-mono font-bold text-info text-center">
                      {ev.pose?.mutualVisibility ?? 0}<span className="text-[10px] opacity-40 ml-1">/1.0</span>
                    </div>
                  </div>
                  <div className="p-3 rounded-2xl bg-bg-deep border border-line">
                    <div className="text-[9px] text-muted uppercase font-bold tracking-widest mb-1 text-center">Pose Δ</div>
                    <div className="text-lg font-mono font-bold text-muted text-center">
                      {ev.pose?.poseDistanceDeg ?? 0}°
                    </div>
                  </div>
                </div>
              </PanelCard>
            </div>

            {/* Verdict */}
            <div className="col-span-12 lg:col-span-3">
              <PanelCard title="👨‍⚖️ Final Verdict" className="h-full bg-accent/5 border-accent/30 shadow-2xl shadow-accent/5">
                <div className="flex flex-col h-full">
                  <div className={`text-center py-6 mb-4 rounded-3xl border ${ev.verdict === 'INSUFFICIENT_DATA' ? 'bg-warn/20 border-warn/40' : 'bg-bg-deep/80 border-accent/20'}`}>
                    <div className="text-[10px] text-muted uppercase font-black tracking-[0.3em] mb-2">Likely Conclusion</div>
                    <div className={`text-lg font-black uppercase tracking-wider ${
                      ev.verdict === 'INSUFFICIENT_DATA' ? 'text-warn' :
                      ev.verdict.includes('H1') ? 'text-danger' : 
                      ev.verdict.includes('H0') ? 'text-success' : 'text-warn'
                    }`}>
                      {ev.verdict === 'INSUFFICIENT_DATA' ? 'INSUFFICIENT DATA' : ev.verdict.split('—')[0]}
                    </div>
                    {ev.verdict === 'INSUFFICIENT_DATA' && (
                      <div className="mt-2 text-[10px] text-warn/80">
                        Coverage too low for reliable verdict
                      </div>
                    )}
                  </div>

                  <div className="space-y-3 flex-1">
                    <VerdictRow label="H0: Same Identity" value={ev.posteriors.H0} color="success" />
                    <VerdictRow label="H1: Mask / Double" value={ev.posteriors.H1} color="danger" />
                    <VerdictRow label="H2: Different Subject" value={ev.posteriors.H2} color="warn" />
                  </div>

                  <div className="mt-8 p-4 rounded-2xl bg-white/5 border border-white/10 italic text-[11px] text-white/60 leading-relaxed">
                    "{ev.geometric?.zoneCount ?? 'N'} zones analyzed with {((ev.dataQuality?.coverageRatio ?? 0.5) * 100).toFixed(0)}% coverage. 
                    {ev.verdict === 'INSUFFICIENT_DATA' ? 'Low confidence — more data needed.' : `Geometric evidence suggests ${ev.verdict.toLowerCase().replace('h0', 'same identity').replace('h1', 'synthetic presence').replace('h2', 'different subject')}.`}"
                  </div>
                </div>
              </PanelCard>
            </div>
          </div>

          {/* [FIX-18] Computation Log for traceability */}
          {ev.computationLog && ev.computationLog.length > 0 && (
            <details className="group mt-6">
              <summary className="list-none flex items-center gap-2 cursor-pointer text-[11px] font-bold text-muted uppercase tracking-widest hover:text-white transition-colors bg-white/5 w-fit px-4 py-2 rounded-full border border-white/5">
                <span className="group-open:rotate-180 transition-transform">▼</span> COMPUTATION LOG (Traceability)
              </summary>
              <div className="mt-4 p-4 rounded-3xl bg-black/60 border border-line overflow-auto max-h-80 custom-scrollbar shadow-inner">
                <div className="space-y-1">
                  {ev.computationLog.map((log, i) => (
                    <div key={i} className="text-[10px] font-mono text-white/70 leading-relaxed flex items-start gap-2">
                      <span className="text-muted shrink-0">[{i + 1}]</span>
                      <span className={
                        log.includes('Verdict:') ? 'text-accent font-bold' :
                        log.includes('ERROR') || log.includes('danger') ? 'text-danger' :
                        log.includes('warn') ? 'text-warn' :
                        'text-info/80'
                      }>{log}</span>
                    </div>
                  ))}
                </div>
              </div>
            </details>
          )}

          {/* Raw JSON for debugging */}
          <details className="group mt-4">
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

function QualityStat({ label, value, target, suffix, raw = false }: { label: string; value: number; target: number; suffix: string; raw?: boolean }) {
  const displayValue = raw ? value : value * 100;
  const displayTarget = raw ? target : target * 100;
  const percentage = raw ? (value / target) : value;
  
  return (
    <div className="space-y-1">
      <div className="flex justify-between items-center px-1">
        <span className="text-[10px] font-bold text-muted uppercase tracking-tighter">{label}</span>
        <span className="text-[11px] font-mono font-bold text-white/90">
          {raw ? displayValue.toFixed(0) : displayValue.toFixed(0)}{suffix}
        </span>
      </div>
      <div className="h-1.5 w-full bg-bg-deep rounded-full overflow-hidden border border-white/5">
        <div 
          className={`h-full rounded-full transition-all duration-1000 ease-out ${
            percentage >= 0.8 ? 'bg-success' : percentage >= 0.5 ? 'bg-warn' : 'bg-danger'
          }`}
          style={{ width: `${Math.min(percentage * 100, 100)}%` }}
        />
      </div>
      {percentage < 0.5 && (
        <div className="text-[9px] text-danger px-1">Below threshold ({(displayTarget * (raw ? 1 : 100)).toFixed(0)}{suffix})</div>
      )}
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
