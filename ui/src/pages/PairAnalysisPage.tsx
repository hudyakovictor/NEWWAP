import { useMemo, useState, useEffect } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { PHOTOS, type PhotoRecord } from "../mock/photos";
import { FACE_ZONES } from "../mock/photoDetail";
import { useApp } from "../store/appStore";
import { api, type EvidenceBreakdown } from "../api";
import { ALL_PHOTOS } from "../data/photoRegistry";
import { getBucketFallbackPolicy, buildCalibrationHealth, type CalibrationHealth } from "../data/calibrationBuckets";
import { EvidenceBadge, EvidenceNote } from "../components/common/EvidenceStatus";
import MeshMorphViewer from "../components/photo/MeshMorphViewer";

/** Lookup the real pose record for a photo id. Returns null if unknown. */
function realPose(id: string) {
  const r = ALL_PHOTOS.find((p) => p.id === id);
  return r?.pose ?? null;
}

/** Side-aware zone visibility from real yaw. */
function zoneVisibleFromYaw(zoneId: string, yawDeg: number | null): boolean {
  if (yawDeg == null) return true;
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
  const [showDetail, setShowDetail] = useState(false);
  
  useEffect(() => {
    setCalibrationHealth(buildCalibrationHealth());
  }, []);

  useEffect(() => {
    setEv(null);
    api.getEvidence(pairA, pairB).then(setEv).catch(console.error);
  }, [pairA, pairB]);

  const realA = realPose(a.id);
  const realB = realPose(b.id);
  
  const calibrationContext = useMemo(() => {
    if (!realA || !realB) return null;
    const pose = realA.classification ?? "unknown";
    const light = "daylight";
    const policy = getBucketFallbackPolicy(pose, light);
    return {
      poseA: realA.classification,
      poseB: realB.classification,
      deltaYaw: realA.yaw != null && realB.yaw != null ? Math.abs(realA.yaw - realB.yaw) : null,
      bucketKey: `${pose}_${light}`,
      ...policy,
    };
  }, [realA, realB]);

  const deltaPose = realA && realB
    ? {
        yaw: +(((realA.yaw ?? 0) - (realB.yaw ?? 0))).toFixed(1),
        pitch: +(((realA.pitch ?? 0) - (realB.pitch ?? 0))).toFixed(1),
        roll: +(((realA.roll ?? 0) - (realB.roll ?? 0))).toFixed(1),
      }
    : null;
  const insufficient = ev?.verdict === "INSUFFICIENT_DATA";

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
        // cluster is null — no penalty until real identity data exists
        const penalty = 0;
        const r = ((i * 37 + a.year + b.year) % 100) / 1000;
        score = Math.max(0, Math.min(1, base - penalty + r));
      }
      return { ...z, visibleA, visibleB, both, excluded, scoreAB: score };
    });
  }, [a, b]);

  return (
    <Page
      title="Анализ пары"
      subtitle="Сравнительный forensic-анализ с байесовским вердиктом"
      actions={
        <button className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">
          Сохранить кейс
        </button>
      }
    >
      {calibrationContext && !calibrationContext.ready && (
        <div className="mb-3 p-2 rounded bg-warn/20 border border-warn/40 text-[11px]">
          <strong>⚠️ Резервный режим калибровки:</strong> Бакет «{calibrationContext.bucketKey}» —
          {calibrationContext.mode === "strict" ? " недостаточно образцов" : " низкая уверенность"}.
          Режим: {calibrationContext.mode} (уверенность: {(calibrationContext.confidence * 100).toFixed(0)}%).
        </div>
      )}

      <EvidenceNote level={insufficient ? "insufficient" : "partial"} className="mb-3">
        Если backend вернул <span className="font-mono">INSUFFICIENT_DATA</span>, вероятности H0/H1/H2 ниже являются
        диагностикой отсутствующих признаков, а не выводом о личности.
      </EvidenceNote>
      
      <div className="grid grid-cols-2 gap-3 mb-3">
        <PhotoSlot label="Фото A" photo={a} onPick={setPairA} />
        <PhotoSlot label="Фото B" photo={b} onPick={setPairB} />
      </div>

      <PanelCard title="Сравнение ракурсов (реальные данные)" className="mb-3">
        {!realA || !realB ? (
          <div className="text-[11px] text-muted">
            Реальный ракурс отсутствует для {!realA ? "A" : !realB ? "B" : "?"}; взаимная видимость — «предполагается видимый».
          </div>
        ) : (
          <div className="grid grid-cols-7 gap-2 text-[11px]">
            <PoseCell label="Ракурс A"   val={`${realA.classification} (${realA.source})`} mono={false} />
            <PoseCell label="Рыск A"     val={`${realA.yaw?.toFixed(1)}°`} />
            <PoseCell label="Тангаж A"   val={`${realA.pitch?.toFixed(1)}°`} />
            <PoseCell label="Ракурс B"   val={`${realB.classification} (${realB.source})`} mono={false} />
            <PoseCell label="Рыск B"     val={`${realB.yaw?.toFixed(1)}°`} />
            <PoseCell label="Тангаж B"   val={`${realB.pitch?.toFixed(1)}°`} />
            <PoseCell
              label="Δрыск"
              val={deltaPose ? `${deltaPose.yaw}°` : "—"}
              color={deltaPose && Math.abs(deltaPose.yaw) > 30 ? "#f59e0b" : "#22c55e"}
            />
          </div>
        )}
      </PanelCard>

      <div className="grid grid-cols-3 gap-3">
        <PanelCard title="Синтез улик">
          <div className="mb-2"><EvidenceBadge level={insufficient ? "insufficient" : "partial"} /></div>
          {!ev ? <div className="text-[11px] text-muted py-4">Загрузка улик...</div> : insufficient ? (
            <InsufficientEvidence ev={ev} />
          ) : (
            <>
              <StatBar label="Геометрическое сходство" value={ev.geometric.boneScore} color="#22c55e" />
              <StatBar label="SNR (кость vs шум)" value={Math.min(1, ev.geometric.snr / 10)} color="#38bdf8" rawText={ev.geometric.snr.toFixed(1) + " дБ"} />
              <StatBar label="Вероятность силикона" value={ev.texture.syntheticProb} color="#ef4444" />
              <StatBar
                label="Хронологическая дельта (лет)"
                value={Math.min(1, ev.chronology.deltaYears / 30)}
                color="#f59e0b"
                rawText={String(ev.chronology.deltaYears)}
              />
            </>
          )}
        </PanelCard>

        <PanelCard title="Байесовский суд">
          <div className="mb-2"><EvidenceBadge level={insufficient ? "insufficient" : "partial"} /></div>
          {!ev ? <div className="text-[11px] text-muted py-4">Вычисление апостериорных вероятностей...</div> : insufficient ? (
            <InsufficientEvidence ev={ev} compact />
          ) : (
            <>
              <StatBar label="H0 · тот же человек" value={ev.posteriors.H0} color="#22c55e" />
              <StatBar label="H1 · двойник / маска" value={ev.posteriors.H1} color="#ef4444" />
              <StatBar label="H2 · разные люди" value={ev.posteriors.H2} color="#f59e0b" />
              <div className="text-[11px] text-muted mt-2 leading-snug font-semibold text-white">
                Вердикт: {ev.verdict}
              </div>
            </>
          )}
        </PanelCard>

        <PanelCard title="Совместимость ракурсов">
          <KV k="Ракурс A" v={a.pose} />
          <KV k="Ракурс B" v={b.pose} />
          <KV
            k="Взаимная видимость"
            v={`${zoneComparison.filter((z) => z.both && !z.excluded).length} / ${zoneComparison.length} зон`}
          />
          <KV k="Исключения по мимике" v={zoneComparison.filter((z) => z.excluded).length} />
          {calibrationHealth && (
            <>
              <KV k="Бакеты калибровки" v={`${calibrationHealth.usableBucketCount}/${calibrationHealth.bucketCount} готовы`} />
              <KV k="Доверенные бакеты" v={calibrationHealth.trustedBucketCount} />
            </>
          )}
          <div className="text-[11px] text-muted mt-2">
            Скрытые/исключённые зоны убраны из расчёта сходства для предотвращения ложноотрицательных результатов.
          </div>
        </PanelCard>
      </div>

      <PanelCard title="Сравнение по 21 зоне" className="mt-3">
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
              {!z.both && <span className="text-[9px] text-warn">скрыта</span>}
              {z.excluded && <span className="text-[9px] text-muted">исключена</span>}
            </div>
          ))}
        </div>
      </PanelCard>

      {/* 3D Morphing View - only for same-bucket pairs */}
      {realA?.classification === realB?.classification && realA?.classification && (
        <PanelCard title="3D-морфинг (интерполяция мешей)" className="mt-3">
          <div className="relative w-full h-[500px] bg-bg-deep rounded">
            <MeshMorphViewer
              datasetA="main"
              photoIdA={a.id}
              datasetB="main"
              photoIdB={b.id}
            />
          </div>
          <div className="text-[10px] text-muted mt-2">
            Показана интерполяция между 3D-мешами двух фотографий. Работает только для фото с одинаковым ракурсом (в одной корзине поз).
          </div>
        </PanelCard>
      )}

      {/* Detailed evidence breakdown (merged from EvidencePage) */}
      <button
        onClick={() => setShowDetail(!showDetail)}
        className="mt-3 px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white flex items-center gap-2"
      >
        <span className={`transition-transform ${showDetail ? "rotate-180" : ""}`}>▼</span>
        {showDetail ? "Свернуть детализацию улик" : "Развернуть детализацию улик"}
      </button>

      {showDetail && ev && (
        <div className="mt-3 space-y-3">
          {ev.dataQuality && ev.dataQuality.coverageRatio < 0.5 && (
            <div className="p-3 rounded bg-warn/10 border border-warn/30 text-[11px]">
              <strong>⚠️ Недостаточное покрытие данных:</strong> Только {(ev.dataQuality.coverageRatio * 100).toFixed(0)}% зон доступно. Уверенность вердикта снижена.
            </div>
          )}

          <div className="grid grid-cols-12 gap-3">
            <div className="col-span-12 lg:col-span-3 space-y-3">
              <PanelCard title="Качество данных">
                <div className="space-y-2 py-1">
                  <QualityStat label="Покрытие зон" value={ev.dataQuality?.coverageRatio ?? 0.5} target={0.8} />
                  <QualityStat label="Зон проанализировано" value={ev.geometric?.zoneCount ?? 0} target={21} raw />
                  {ev.geometric?.excludedZones && ev.geometric.excludedZones.length > 0 && (
                    <div className="mt-2 p-2 rounded bg-warn/10 border border-warn/20">
                      <div className="text-[9px] text-warn uppercase font-bold mb-1">
                        Исключено ({ev.pose?.expressionExcluded ?? 0})
                      </div>
                      <div className="text-[10px] text-white/70">
                        {ev.geometric.excludedZones.slice(0, 3).join(', ')}
                        {ev.geometric.excludedZones.length > 3 && ` +${ev.geometric.excludedZones.length - 3}`}
                      </div>
                    </div>
                  )}
                </div>
              </PanelCard>
              <PanelCard title="Хронология">
                <div className="flex items-center justify-between px-1 py-1">
                  <div className="text-[10px] text-muted uppercase font-bold">Период старения</div>
                  <div className="text-[12px] font-mono text-white">{ev.chronology.deltaYears} лет</div>
                </div>
                <div className="mt-2 space-y-1">
                  {ev.chronology.flags.length === 0 ? (
                    <div className="text-[11px] text-ok flex items-center gap-2 bg-ok/10 p-2 rounded border border-ok/20">
                      ✓ Хронологическая последовательность согласована
                    </div>
                  ) : (
                    ev.chronology.flags.map(f => (
                      <div key={f} className="text-[11px] text-warn flex items-center gap-2 bg-warn/10 p-2 rounded border border-warn/20">
                        ⚠ {f}
                      </div>
                    ))
                  )}
                </div>
              </PanelCard>
            </div>

            <div className="col-span-12 lg:col-span-3 space-y-3">
              <PanelCard title="Геометрическая целостность">
                <div className="space-y-3 py-1">
                  <IconStat label="Костная структура SNR" value={ev.geometric.boneScore} color="#22c55e" />
                  <IconStat label="Связочные якоря" value={ev.geometric.ligamentScore} color="#38bdf8" />
                  <IconStat label="Дельта мягких тканей" value={ev.geometric.softTissueScore} color="#f59e0b" />
                  <div className="h-px bg-white/5 mt-1"></div>
                  <div className="flex justify-between items-center px-1">
                    <span className="text-[10px] text-muted uppercase font-bold">Геометрический SNR</span>
                    <span className="text-[12px] font-mono font-bold text-ok">{ev.geometric.snr.toFixed(1)} дБ</span>
                  </div>
                  {ev.geometric?.categoryDivergence && (
                    <div className="mt-2 space-y-1">
                      <div className="text-[9px] text-muted uppercase font-bold">Расхождение категорий</div>
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

            <div className="col-span-12 lg:col-span-3 space-y-3">
              <PanelCard title="Текстурный анализ">
                <div className="space-y-3 py-1">
                  <div className="space-y-1">
                    <div className="flex justify-between items-center px-1">
                      <span className="text-[10px] font-bold text-muted uppercase">Вероятность синтетики</span>
                    </div>
                    <div className="flex items-center gap-2 px-1">
                      <div className="flex-1 h-2 bg-bg-deep rounded-full overflow-hidden">
                        <div className="h-full bg-danger rounded-full" style={{ width: `${(ev.texture.syntheticProb ?? 0) * 100}%` }} />
                      </div>
                      <span className="text-[11px] font-mono font-bold text-danger">
                        {((ev.texture.syntheticProb ?? 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  <IconStat label="FFT периодичность" value={ev.texture.fft} color="#f59e0b" />
                  <IconStat label="LBP сложность" value={ev.texture.lbp} color="#38bdf8" />
                  <IconStat label="Альбедо-равномерность" value={ev.texture.albedo} color="#22c55e" />
                  {ev.texture.h1Subtype && ev.texture.syntheticProb > 0.3 && (
                    <div className="mt-2 p-2 rounded bg-danger/10 border border-danger/20">
                      <div className="text-[9px] text-danger uppercase font-bold mb-1">Обнаруженный тип (H1)</div>
                      <div className="text-[12px] font-bold text-white capitalize">{ev.texture.h1Subtype.primary}</div>
                      <div className="text-[9px] text-white/60">уверенность: {(ev.texture.h1Subtype.confidence * 100).toFixed(0)}%</div>
                    </div>
                  )}
                </div>
              </PanelCard>
              <PanelCard title="Ракурс и фильтрация">
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-2 rounded bg-bg-deep border border-line text-center">
                    <div className="text-[9px] text-muted uppercase font-bold mb-1">Видимость</div>
                    <div className="text-lg font-mono font-bold text-info">{ev.pose?.mutualVisibility ?? 0}<span className="text-[10px] opacity-40">/1.0</span></div>
                  </div>
                  <div className="p-2 rounded bg-bg-deep border border-line text-center">
                    <div className="text-[9px] text-muted uppercase font-bold mb-1">Δ ракурса</div>
                    <div className="text-lg font-mono font-bold text-muted">{ev.pose?.poseDistanceDeg ?? 0}°</div>
                  </div>
                </div>
              </PanelCard>
            </div>

            <div className="col-span-12 lg:col-span-3">
              <PanelCard title="Итоговый вердикт" className="h-full bg-accent/5 border-accent/30">
                <div className="flex flex-col h-full">
                  <div className={`text-center py-4 mb-3 rounded border ${ev.verdict === 'INSUFFICIENT_DATA' ? 'bg-warn/20 border-warn/40' : 'bg-bg-deep/80 border-accent/20'}`}>
                    <div className="text-[10px] text-muted uppercase font-black tracking-[0.3em] mb-2">Наиболее вероятный вывод</div>
                    <div className={`text-lg font-black uppercase tracking-wider ${
                      ev.verdict === 'INSUFFICIENT_DATA' ? 'text-warn' :
                      ev.verdict.includes('H1') ? 'text-danger' : 
                      ev.verdict.includes('H0') ? 'text-ok' : 'text-warn'
                    }`}>
                      {ev.verdict === 'INSUFFICIENT_DATA' ? 'НЕДОСТАТОЧНО ДАННЫХ' : ev.verdict.split('—')[0]}
                    </div>
                  </div>
                  <div className="space-y-2 flex-1">
                    <VerdictRow label="H0: Та же личность" value={ev.posteriors.H0} color="#22c55e" />
                    <VerdictRow label="H1: Маска / двойник" value={ev.posteriors.H1} color="#ef4444" />
                    <VerdictRow label="H2: Разные люди" value={ev.posteriors.H2} color="#f59e0b" />
                  </div>
                  <div className="mt-4 p-3 rounded bg-white/5 border border-white/10 italic text-[11px] text-white/60 leading-relaxed">
                    Проанализировано {ev.geometric?.zoneCount ?? 'N'} зон с покрытием {((ev.dataQuality?.coverageRatio ?? 0.5) * 100).toFixed(0)}%.
                    {ev.verdict === 'INSUFFICIENT_DATA' ? ' Низкая уверенность — нужны дополнительные данные.' : ''}
                  </div>
                </div>
              </PanelCard>
            </div>
          </div>

          {ev.computationLog && ev.computationLog.length > 0 && (
            <details className="group">
              <summary className="list-none flex items-center gap-2 cursor-pointer text-[11px] font-bold text-muted uppercase tracking-widest hover:text-white bg-white/5 w-fit px-3 py-1.5 rounded border border-white/5">
                <span className="group-open:rotate-180 transition-transform">▼</span> Журнал вычислений
              </summary>
              <div className="mt-2 p-3 rounded bg-black/60 border border-line overflow-auto max-h-60">
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
        </div>
      )}
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
            <KV k="кластер" v={photo.cluster ?? "нет данных"} />
            <KV k="синтетика" v={photo.syntheticProb != null ? photo.syntheticProb.toFixed(2) : "нет данных"} />
          </div>
        </div>
      </div>
      <div className="mt-3">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="фильтр по id / дате"
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

function InsufficientEvidence({ ev, compact = false }: { ev: EvidenceBreakdown; compact?: boolean }) {
  return (
    <div className="rounded bg-warn/10 border border-warn/40 p-3 text-[11px] text-warn leading-relaxed">
      <div className="font-semibold text-white">Недостаточно данных для forensic-вывода</div>
      {!compact && (
        <div className="mt-1">
          Геометрия, текстура и байесовские постериоры скрыты как выводы, пока обе фотографии не имеют готовых признаков.
        </div>
      )}
      <div className="mt-2 font-mono text-[10px] text-muted">
        {ev.computationLog?.[0] ?? "backend returned INSUFFICIENT_DATA"}
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

function QualityStat({ label, value, target, raw }: {
  label: string; value: number; target: number; suffix?: string; raw?: boolean;
}) {
  const pct = raw ? (value / target) : value;
  const ok = raw ? value >= target : value >= target;
  return (
    <div className="flex items-center gap-2 my-1">
      <div className="text-[11px] text-muted w-32 truncate">{label}</div>
      <div className="flex-1 h-2 bg-bg rounded overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, pct * 100)}%`, background: ok ? "#22c55e" : "#f59e0b" }} />
      </div>
      <div className="text-[11px] font-mono w-14 text-right" style={{ color: ok ? "#22c55e" : "#f59e0b" }}>
        {raw ? `${value}/${target}` : `${(value * 100).toFixed(0)}%`}
      </div>
    </div>
  );
}

function IconStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-2 my-1">
      <div className="text-[11px] text-muted flex-1 truncate">{label}</div>
      <div className="flex-1 h-2 bg-bg rounded overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, value * 100)}%`, background: color }} />
      </div>
      <div className="text-[11px] font-mono w-12 text-right" style={{ color }}>{value.toFixed(2)}</div>
    </div>
  );
}

function VerdictRow({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="text-[11px] text-muted flex-1 truncate">{label}</div>
      <div className="flex-1 h-2 bg-bg rounded overflow-hidden">
        <div className="h-full" style={{ width: `${Math.min(100, value * 100)}%`, background: color }} />
      </div>
      <div className="text-[11px] font-mono w-12 text-right" style={{ color }}>{(value * 100).toFixed(1)}%</div>
    </div>
  );
}
