import { useRef, useEffect, useState, useMemo, useCallback } from "react";
import {
  buildPhotoPoints,
  metrics,
  eventMarkers,
  photoVolume,
  YEARS,
} from "../../mock/data";
import PhotoStrip from "./PhotoStrip";
import { SeverityIcon, EventIcon } from "./icons";
import { evidenceOf } from "../../data/evidencePolicy";
import { EvidenceNote } from "../../components/common/EvidenceStatus";

const LABEL_W = 168;
const THUMB_SIZE = 50;
const METRIC_ROW_H = 60; // taller to fit graphs
const VB_H = 100; // viewBox height for SVG

export default function TimelineView() {
  const [selectedIndex, setSelectedIndex] = useState(() => {
    const points = buildPhotoPoints();
    const idx2012 = points.findIndex(p => p.year === 2012);
    return idx2012 >= 0 ? idx2012 : 0;
  });
  const [poseFilter, setPoseFilter] = useState<string>("");
  const [zoom, setZoom] = useState<number>(1);

  const photoPoints = useMemo(() =>
    buildPhotoPoints(poseFilter || undefined),
    [poseFilter]
  );

  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey || e.shiftKey) {
      e.preventDefault();
      const delta = e.deltaY > 0 ? -0.2 : 0.2;
      setZoom(prev => Math.max(0.5, Math.min(3, prev + delta)));
    }
  }, []);

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const gapSize = Math.max(2, 4 * zoom);
    const colWidth = THUMB_SIZE + gapSize;
    const xCenter = LABEL_W + selectedIndex * colWidth + colWidth / 2;
    el.scrollTo({ left: xCenter - el.clientWidth / 2, behavior: "smooth" });
  }, [selectedIndex, zoom]);

  const selectedPoint = photoPoints[selectedIndex];

  const gapSize = Math.max(2, 4 * zoom);
  const colWidth = THUMB_SIZE + gapSize;
  const totalWidth = LABEL_W + photoPoints.length * colWidth + 20;

  // Align all metrics to photoPoints
  const processedMetrics = useMemo(() => {
    return metrics.map(m => {
      let values: number[] = [];
      let flags: (string | undefined)[] = [];

      if (m.values.length === photoPoints.length) {
        // Already per-photo
        values = m.values;
        flags = m.flags || [];
      } else {
        // Per-year (27 values), need to expand to match photos
        photoPoints.forEach((p) => {
          const yearIdx = YEARS.indexOf(p.year);
          values.push(m.values[yearIdx] ?? 0);
          flags.push(m.flags?.[yearIdx]);
        });
      }

      // Calculate domain if not provided
      const [dmin, dmax] = m.domain ?? [Math.min(...values), Math.max(...values)];
      
      return { ...m, values, flags, dmin, dmax };
    });
  }, [photoPoints]);

  const getY = (v: number, dmin: number, dmax: number) => {
    const pad = 10;
    const range = dmax - dmin || 1;
    const t = (v - dmin) / range;
    return VB_H - pad - t * (VB_H - pad * 2);
  };

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-[#0a1523]">
      {/* Header */}
      <div className="px-3 py-2 flex justify-between items-center border-b border-[#1a2b44]/60 shrink-0">
        <div className="text-sm font-medium text-white/90 flex items-center gap-3">
          Таймлайн расследования — {photoPoints.length} точек улик
          <EvidenceNote level={evidenceOf("timeline_metrics")?.level ?? "stub"} />
        </div>
        <div className="flex items-center gap-4">
          <select
            value={poseFilter}
            onChange={e => setPoseFilter(e.target.value)}
            className="bg-[#0d1b2d] border border-[#1a2b44] rounded px-2 py-1 text-xs text-[#6b7a90] focus:outline-none"
          >
            <option value="">Все ракурсы</option>
            <option value="frontal">Фронтальный</option>
            <option value="three_quarter_left">3/4 слева</option>
            <option value="three_quarter_right">3/4 справа</option>
            <option value="profile_left">Профиль слева</option>
            <option value="profile_right">Профиль справа</option>
          </select>
        </div>
      </div>

      {/* Selected photo detail strip */}
      {selectedPoint && (
        <div className="px-4 py-2 border-b border-[#1a2b44]/40 bg-[#0d1b2d]/40 shrink-0 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="relative group">
              <img src={selectedPoint.photo} alt="" className="w-12 h-12 rounded border border-[#1a2b44] object-cover" />
              <div className="absolute inset-0 bg-accent/20 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none rounded" />
            </div>
            <div>
              <div className="text-sm font-bold text-white flex items-center gap-2">
                {selectedPoint.year} 
                <span className="px-1.5 py-0.5 rounded text-[10px] bg-bg-deep border border-line/40 text-muted uppercase">
                  {selectedPoint.pose.classification.replace(/_/g, ' ')}
                </span>
                {selectedPoint.anomaly && <SeverityIcon s={selectedPoint.anomaly} />}
              </div>
              <div className="text-[11px] font-mono text-[#6b7a90]">
                РЫСК.: {selectedPoint.pose.yaw?.toFixed(1) ?? '?'}° ·
                ТАНГАЖ: {selectedPoint.pose.pitch?.toFixed(1) ?? '?'}° ·
                ИСТОЧНИК: {selectedPoint.pose.source.toUpperCase()}
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-muted uppercase tracking-tighter mb-0.5">Прогресс расследования</div>
            <div className="flex items-center gap-1">
              <div className="h-1 w-24 bg-line/20 rounded-full overflow-hidden">
                <div className="h-full bg-accent" style={{ width: `${(selectedIndex / photoPoints.length) * 100}%` }} />
              </div>
              <span className="text-[10px] font-mono text-muted">{selectedIndex + 1}/{photoPoints.length}</span>
            </div>
          </div>
        </div>
      )}

      {/* Main Scrollable Area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-x-auto overflow-y-auto bg-bg-deep custom-scrollbar"
        onWheel={handleWheel}
      >
        <div style={{ width: totalWidth, minHeight: "100%" }} className="flex flex-col">
          
          {/* Year Header Row */}
          <div className="flex shrink-0 sticky top-0 z-30 bg-[#0a1523]/95 backdrop-blur-md border-b border-line/60 h-[24px]">
            <div style={{ width: LABEL_W }} className="shrink-0 px-3 flex items-center border-r border-line/60">
              <span className="text-[9px] text-muted uppercase font-bold tracking-widest">Хронология</span>
            </div>
            <div className="flex relative">
              {photoPoints.map((p, idx) => {
                const showLabel = idx === 0 || p.year !== photoPoints[idx - 1]?.year;
                if (!showLabel) return <div key={idx} style={{ width: colWidth }} className="shrink-0" />;
                const yearCount = photoPoints.filter(x => x.year === p.year).length;
                return (
                  <div key={idx} style={{ width: colWidth * yearCount }} className="shrink-0 border-l border-line/30 px-1 flex items-center h-full">
                    <span className="text-[10px] text-white/60 font-mono">{p.year}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Photo Strip */}
          <div className="shrink-0 py-2 border-b border-line/40 bg-bg-panel/20">
            <PhotoStrip
              points={photoPoints}
              selectedIndex={selectedIndex}
              onSelect={setSelectedIndex}
              zoom={zoom}
            />
          </div>

          {/* Identity & Events Rows (Year-based logic mapped to photos) */}
          <div className="shrink-0 border-b border-line/40">
            <div className="flex items-center h-8">
              <div style={{ width: LABEL_W }} className="px-3 border-r border-line/60 shrink-0 flex flex-col justify-center">
                <span className="text-[10px] text-white/80">Кластер идентичности</span>
              </div>
              <div className="flex h-full items-center">
                {photoPoints.map((p, i) => (
                  <div key={i} style={{ width: colWidth }} className="h-full flex items-center justify-center">
                    {p.identity ? (
                      <div className={`w-3 h-3 rounded-full border-2 ${p.identity === 'A' ? 'bg-accent border-accent/40' : 'bg-danger border-danger/40'}`} />
                    ) : (
                      <div className="w-3 h-3 rounded-full border border-line/30 bg-transparent" title="Нет данных" />
                    )}
                  </div>
                ))}
              </div>
            </div>
            <div className="flex items-center h-8 border-t border-line/20">
              <div style={{ width: LABEL_W }} className="px-3 border-r border-line/60 shrink-0 flex flex-col justify-center">
                <span className="text-[10px] text-white/80">События</span>
              </div>
              <div className="flex h-full items-center">
                {photoPoints.map((p, i) => {
                  const event = eventMarkers.find(e => e.year === p.year && (i === 0 || p.year !== photoPoints[i-1].year));
                  return (
                    <div key={i} style={{ width: colWidth }} className="h-full flex items-center justify-center" title={event?.title}>
                      {event && <EventIcon kind={event.kind} />}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Metric Rows with SVGs */}
          <div className="flex flex-col bg-bg-deep">
            {processedMetrics.map((m) => {
              const svgPath = m.values.map((v, i) => {
                const x = i * colWidth + THUMB_SIZE / 2;
                const y = getY(v, m.dmin, m.dmax);
                return `${i === 0 ? "M" : "L"}${x},${y}`;
              }).join(" ");

              return (
                <div key={m.id} className="flex border-b border-line/20 hover:bg-white/[0.02] transition-colors group">
                  <div style={{ width: LABEL_W }} className="shrink-0 px-3 py-2 border-r border-line/60 flex flex-col justify-center">
                    <div className="text-[11px] text-white/90 truncate font-medium">{m.title}</div>
                    <div className="text-[9px] text-muted truncate uppercase tracking-tighter">{m.subtitle || 'Метрика'}</div>
                  </div>
                  <div className="relative" style={{ height: METRIC_ROW_H, width: photoPoints.length * colWidth }}>
                    {/* SVG Layer */}
                    <svg className="absolute inset-0 w-full h-full pointer-events-none overflow-visible">
                      {m.kind === 'bar' ? (
                        m.values.map((v, i) => {
                          const x = i * colWidth + THUMB_SIZE / 2 - 2;
                          const y = getY(v, m.dmin, m.dmax);
                          return (
                            <rect key={i} x={x} y={y} width={4} height={VB_H - y - 10} fill={m.color} opacity={0.4} />
                          );
                        })
                      ) : (
                        <path d={svgPath} stroke={m.color} fill="none" strokeWidth={1.5} strokeLinejoin="round" opacity={0.6} />
                      )}
                    </svg>

                    {/* Interaction & Values Layer */}
                    <div className="absolute inset-0 flex">
                      {photoPoints.map((_, i) => {
                        const isSelected = i === selectedIndex;
                        const v = m.values[i];
                        const flag = m.flags[i];
                        return (
                          <button
                            key={i}
                            onClick={() => setSelectedIndex(i)}
                            style={{ width: THUMB_SIZE, marginRight: gapSize }}
                            className={`h-full flex flex-col items-center justify-between pt-1 pb-1.5 shrink-0 transition-all ${
                              isSelected ? 'bg-accent/5' : 'hover:bg-white/[0.03]'
                            }`}
                          >
                            <span className={`text-[9px] font-mono transition-colors ${isSelected ? 'text-white font-bold scale-110' : 'text-[#6b7a90] group-hover:text-muted'}`}>
                              {v.toFixed(v < 10 ? (v < 1 ? 2 : 1) : 0)}
                            </span>
                            {isSelected && (
                              <div className="w-1 h-1 rounded-full bg-accent animate-pulse" />
                            )}
                            {flag && <div className="absolute bottom-1"><SeverityIcon s={flag as any} /></div>}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Bottom Scrubber / Navigator */}
      <div className="h-12 bg-bg-deep border-t border-line/60 px-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <div className="text-[10px] text-muted uppercase tracking-widest font-bold">Навигатор расследования</div>
          <div className="flex gap-1 h-4">
            {photoVolume.slice(0, 27).map((v, i) => (
              <div key={i} className="w-1 bg-accent/40 rounded-t-sm self-end" style={{ height: `${(v / 100) * 100}%` }} />
            ))}
          </div>
        </div>
        <div className="text-[10px] text-muted font-mono">
          ПРОКРУТКА: ПЕРЕМЕЩЕНИЕ · CTRL+ПРОКРУТКА: МАСШТАБ · КЛИК: ВЫБОР УЛИКИ
        </div>
      </div>
    </div>
  );
}
