import { useMemo, useState, useCallback, useEffect } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { type PhotoRecord } from "../mock/photos";
import PhotoDetailModal from "../components/photo/PhotoDetailModal";
import UploadModal from "../components/upload/UploadModal";
import { useApp } from "../store/appStore";
import { api } from "../api";
import { EvidenceBadge, EvidenceNote } from "../components/common/EvidenceStatus";

const POSE_GROUPS = ["frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right", "none"] as const;
const FOLDER_OPTIONS = ["any", "main", "myface"] as const;
const POSE_SOURCE_OPTIONS = ["any", "hpe", "3ddfa", "none"] as const;
const DATASET_TABS = ["main", "calibration"] as const;

const POSE_LABELS: Record<string, string> = {
  frontal: "Фронтальный",
  three_quarter_left: "3/4 лево",
  three_quarter_right: "3/4 право",
  profile_left: "Профиль лево",
  profile_right: "Профиль право",
  none: "Без ракурса",
};

/** A photo is "processed" if it has pose data from at least one detector. */
function isProcessed(p: PhotoRecord): boolean {
  return p.poseSource !== "none";
}

export default function PhotosPage() {
  const [photos, setPhotos] = useState<PhotoRecord[]>([]);
  const [query, setQuery] = useState("");
  const [selectedYear, setSelectedYear] = useState<number | "all">("all");
  const [folder, setFolder] = useState<(typeof FOLDER_OPTIONS)[number]>("main");
  const [poseSource, setPoseSource] = useState<(typeof POSE_SOURCE_OPTIONS)[number]>("any");
  const [maxYaw, setMaxYaw] = useState(90);
  const [opened, setOpened] = useState<PhotoRecord | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [extracting, setExtracting] = useState(false);
  const [extractNotice, setExtractNotice] = useState<string | null>(null);
  const [datasetTab, setDatasetTab] = useState<(typeof DATASET_TABS)[number]>("main");
  const { setPage } = useApp();

  useEffect(() => {
    api.listPhotos({}).then((res) => {
      setPhotos(res.items);
    }).catch(console.error);
  }, []);

  const availableYears = useMemo(() => {
    const years = Array.from(new Set(photos.map(p => p.year || p.parsed_year).filter(y => y > 0))).sort((a, b) => a - b);
    return years;
  }, [photos]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return photos.filter((p) => {
      const pFolder = p.folder || p.dataset || "main";
      const pId = p.id || p.photo_id || "";
      const pDate = p.date || p.date_str || "";
      const pYaw = p.yaw ?? p.pose?.yaw ?? null;
      const pYear = p.year || p.parsed_year || 0;

      // Auto-filter by dataset tab
      if (datasetTab === "main" && pFolder !== "main") return false;
      if (datasetTab === "calibration" && pFolder !== "myface") return false;

      if (q && !pId.toLowerCase().includes(q) && !pDate.includes(q)) return false;
      if (selectedYear !== "all" && pYear !== selectedYear) return false;
      if (folder !== "any" && pFolder !== folder) return false;
      if (poseSource !== "any" && (p.poseSource || p.pose?.source || "none") !== poseSource) return false;
      if (pYaw !== null && Math.abs(pYaw) > maxYaw) return false;
      return true;
    });
  }, [photos, query, selectedYear, folder, poseSource, maxYaw, datasetTab]);

  const grouped = useMemo(() => {
    const groups: Record<string, PhotoRecord[]> = {};
    POSE_GROUPS.forEach(g => groups[g] = []);
    
    filtered.forEach(p => {
      const g = p.pose || "none";
      if (!groups[g]) groups[g] = [];
      groups[g].push(p);
    });

    Object.keys(groups).forEach(g => {
      groups[g].sort((a, b) => (a.date || "") < (b.date || "") ? -1 : 1);
    });

    return groups;
  }, [filtered]);

  const stats = useMemo(() => {
    const processed = filtered.filter(isProcessed).length;
    const unprocessed = filtered.length - processed;
    const calib = filtered.filter(p => p.folder === "myface").length;
    return { total: filtered.length, processed, unprocessed, calib };
  }, [filtered]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelectedIds(new Set(filtered.map(p => p.id)));
  }, [filtered]);

  const selectByPose = useCallback((pose: string) => {
    setSelectedIds(new Set(filtered.filter(p => p.pose === pose).map(p => p.id)));
  }, [filtered]);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  async function runExtract(mode: "selected" | "all" | "by_pose", pose?: string) {
    setExtracting(true);
    setExtractNotice(null);
    try {
      let ids: string[] = [];
      if (mode === "selected") {
        ids = Array.from(selectedIds);
      } else if (mode === "all") {
        ids = filtered.map(p => p.id);
      } else if (mode === "by_pose" && pose) {
        ids = filtered.filter(p => p.pose === pose).map(p => p.id);
      }
      if (ids.length === 0) return;
      const dataset = datasetTab === "calibration" ? "calibration" : "main";
      await api.startJob("extract", { dataset, onlyIds: ids, limit: ids.length });
      setExtractNotice(
        `Задача извлечения запущена для ${ids.length} фото. Датасет: ${dataset}.`
      );
    } finally {
      setExtracting(false);
    }
  }

  return (
    <Page
      title="Фотоархив"
      subtitle={`${photos.length} всего · ${filtered.length} по фильтру · ${stats.processed} обработано · ${stats.unprocessed} не обработано`}
      actions={
        <div className="flex gap-2">
          <button
            onClick={() => setShowUpload(true)}
            className="px-4 h-9 rounded-full bg-white/10 hover:bg-white/20 transition-all text-[12px] font-medium text-white border border-white/10"
          >
            + Импорт
          </button>
          <button
            onClick={() => setPage("jobs")}
            className="px-4 h-9 rounded-full bg-accent/80 hover:bg-accent transition-all text-[12px] font-medium text-white shadow-lg shadow-accent/20"
          >
            Статус конвейера
          </button>
        </div>
      }
    >
      {/* Dataset Tabs */}
      <div className="flex gap-2 mb-4">
        {DATASET_TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setDatasetTab(tab)}
            className={`px-4 h-9 rounded-lg text-[12px] font-medium transition-all ${
              datasetTab === tab
                ? "bg-accent text-white shadow-lg shadow-accent/20"
                : "bg-white/10 hover:bg-white/20 text-white border border-white/10"
            }`}
          >
            {tab === "main" ? "Основной датасет" : "Калибровочный датасет"}
          </button>
        ))}
      </div>
      {/* Stats bar */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <MiniStat label="Всего фото" value={stats.total} color="#cfd8e6" />
        <MiniStat label="Обработано" value={stats.processed} color="#22c55e" />
        <MiniStat label="Не обработано" value={stats.unprocessed} color="#6b7a90" />
        <MiniStat label="Калибровочных" value={stats.calib} color="#a855f7" />
      </div>

      <EvidenceNote level="real" className="mb-4">
        Эта страница — навигация по реальным фото и pose-сигналам. Серые карточки означают отсутствие pose,
        а не доказательство подделки. Синтетические флаги старого mock-слоя нельзя трактовать как forensic-вывод
        до полного pipeline-прогона.
      </EvidenceNote>

      {extractNotice && (
        <div className="mb-4 rounded-xl border border-warn/40 bg-warn/10 p-3 text-[11px] text-warn">
          {extractNotice}
        </div>
      )}

      {/* Year Selection Timeline */}
      <div className="mb-4 p-3 rounded-xl bg-bg-deep/50 border border-line/50">
        <div className="flex items-center justify-between mb-2 px-1">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted/80">Фильтр по хронологии</span>
          <span className="text-[11px] font-mono text-info bg-info/10 px-2 py-0.5 rounded-full">
            {selectedYear === "all" ? "Все годы" : `Год: ${selectedYear}`}
          </span>
        </div>
        <div className="flex gap-1 overflow-x-auto pb-1 scrollbar-none no-scrollbar">
          <button
            onClick={() => setSelectedYear("all")}
            className={`flex-shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-mono transition-all ${
              selectedYear === "all" 
                ? "bg-accent text-white shadow-md shadow-accent/20" 
                : "bg-bg-deep text-muted hover:text-white border border-white/5"
            }`}
          >
            ВСЕ
          </button>
          {availableYears.map(y => (
            <button
              key={y}
              onClick={() => setSelectedYear(y)}
              className={`flex-shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-mono transition-all ${
                selectedYear === y 
                  ? "bg-accent text-white shadow-md shadow-accent/20" 
                  : "bg-bg-deep text-muted hover:text-white border border-white/5"
              }`}
            >
              {y}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
        <div className="md:col-span-1">
          <PanelCard title="Фильтры метаданных" className="h-full">
            <div className="flex flex-col gap-4 text-[11px]">
              <Field label="Поиск по тексту">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="ID или дата..."
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line focus:border-accent transition-colors text-white outline-none"
                />
              </Field>
              <Field label="Раздел данных">
                <Select value={folder} onChange={setFolder as any} options={FOLDER_OPTIONS} />
              </Field>
              <Field label="Источник детекции">
                <Select value={poseSource} onChange={setPoseSource as any} options={POSE_SOURCE_OPTIONS} />
              </Field>
              <Field label={`Порог угла: |рыск| ≤ ${maxYaw}°`}>
                <div className="px-1">
                  <input
                    type="range"
                    min={0}
                    max={90}
                    step={1}
                    value={maxYaw}
                    onChange={(e) => setMaxYaw(+e.target.value)}
                    className="w-full accent-accent"
                  />
                  <div className="flex justify-between mt-1 text-[9px] text-muted font-mono uppercase">
                    <span>Фронтальный</span>
                    <span>Профиль</span>
                  </div>
                </div>
              </Field>

              {/* Extraction controls */}
              <div className="border-t border-line/40 pt-3 space-y-2">
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted">Извлечение признаков</div>
                <div className="text-[10px] text-info leading-snug">
                  Выбор фото передаётся в backend как <span className="font-mono">only_ids</span>. Для калибровочных фото используется dataset calibration.
                </div>
                <button
                  onClick={() => runExtract("selected")}
                  disabled={selectedIds.size === 0 || extracting}
                  className="w-full h-8 rounded-lg bg-info/70 hover:bg-info text-[11px] text-white disabled:opacity-40 transition-colors"
                >
                  Извлечь выбранные ({selectedIds.size})
                </button>
                <button
                  onClick={() => runExtract("all")}
                  disabled={extracting}
                  className="w-full h-8 rounded-lg bg-accent/70 hover:bg-accent text-[11px] text-white disabled:opacity-40 transition-colors"
                >
                  Извлечь все ({filtered.length})
                </button>
                <div className="text-[9px] text-muted mt-1">По ракурсу:</div>
                <div className="grid grid-cols-2 gap-1">
                  {POSE_GROUPS.filter(g => g !== "none").map(pose => (
                    <button
                      key={pose}
                      onClick={() => runExtract("by_pose", pose)}
                      disabled={extracting}
                      className="h-6 rounded bg-line/60 hover:bg-line text-[9px] text-white disabled:opacity-40 truncate px-1"
                    >
                      {POSE_LABELS[pose]}
                    </button>
                  ))}
                </div>
              </div>

              {/* Selection controls */}
              <div className="border-t border-line/40 pt-3 space-y-1">
                <div className="text-[10px] font-bold uppercase tracking-wider text-muted">Выделение</div>
                <div className="flex gap-1">
                  <button onClick={selectAll} className="flex-1 h-6 rounded bg-line/60 hover:bg-line text-[9px] text-white">Все</button>
                  <button onClick={clearSelection} className="flex-1 h-6 rounded bg-line/60 hover:bg-line text-[9px] text-white">Сброс</button>
                </div>
                <div className="grid grid-cols-2 gap-1">
                  {POSE_GROUPS.filter(g => g !== "none").map(pose => (
                    <button
                      key={pose}
                      onClick={() => selectByPose(pose)}
                      className="h-5 rounded bg-line/40 hover:bg-line/60 text-[8px] text-white truncate px-1"
                    >
                      {POSE_LABELS[pose]}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </PanelCard>
        </div>

        <div className="md:col-span-3 space-y-6">
          {/* Legend */}
          <div className="flex items-center gap-4 text-[10px] text-muted px-1">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-white/80 border border-line inline-block" /> Обработано</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-muted/40 border border-line inline-block" /> Не обработано (ч/б)</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-purple-500/40 border border-purple-400/60 inline-block" /> Калибровочное</span>
          </div>

          {POSE_GROUPS.map(group => {
            const items = grouped[group] || [];
            if (items.length === 0) return null;

            return (
              <div key={group} className="relative">
                <div className="flex items-center gap-3 mb-3">
                  <h3 className="text-[12px] font-bold text-white uppercase tracking-[0.2em] bg-bg-deep px-3 py-1 rounded-full border border-line shadow-sm">
                    {POSE_LABELS[group] || group}
                  </h3>
                  <div className="h-px flex-1 bg-gradient-to-r from-line to-transparent"></div>
                  <span className="text-[10px] font-mono text-muted">{items.length} фото</span>
                </div>
                
                <div className="flex gap-3 overflow-x-auto pb-3 scrollbar-thin scrollbar-thumb-white/10 hover:scrollbar-thumb-white/20 transition-all">
                  {items.map((p) => {
                    const pId = p.id || p.photo_id || "";
                    const pFolder = p.folder || p.dataset || "main";
                    const pDate = p.date || p.date_str || "Дата неизвестна";
                    const pPhoto = p.photo || p.source_url || "";
                    const pYaw = p.yaw ?? p.pose?.yaw ?? null;
                    const pPoseSource = p.poseSource || p.pose?.source || "none";

                    const processed = pPoseSource !== "none";
                    const isCalib = pFolder === "myface";
                    const isSelected = selectedIds.has(pId);
                    return (
                      <button
                        key={pId}
                        onClick={(e) => {
                          if (e.shiftKey) {
                            toggleSelect(pId);
                          } else {
                            setOpened(p);
                          }
                        }}
                        className={`flex-shrink-0 w-[155px] relative group rounded-2xl overflow-hidden border text-left transition-all hover:translate-y-[-2px] hover:shadow-xl ${
                          isSelected
                            ? "border-info ring-2 ring-info/50"
                            : isCalib
                            ? "border-purple-400/40 hover:border-purple-400/70"
                            : "border-line/50 hover:border-accent/50"
                        } bg-bg-deep`}
                      >
                        <div className="aspect-[3/4] overflow-hidden relative">
                          <img 
                            src={pPhoto} 
                            alt={pId} 
                            className={`w-full h-full object-cover transition-transform duration-500 group-hover:scale-110 ${
                              !processed ? "grayscale opacity-70" : ""
                            }`} 
                            loading="lazy" 
                          />
                          {/* Calibration badge */}
                          {isCalib && (
                            <div className="absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded bg-purple-500/80 text-[8px] text-white font-bold">
                              КАЛИБР
                            </div>
                          )}
                          {/* Selection checkbox */}
                          <div className={`absolute top-1.5 left-1.5 w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${
                            isSelected ? "border-info bg-info" : "border-white/30 bg-black/30 opacity-0 group-hover:opacity-100"
                          }`}>
                            {isSelected && <span className="text-[8px] text-white">✓</span>}
                          </div>
                          {/* Unprocessed overlay */}
                          {!processed && (
                            <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/90 to-transparent p-2">
                              <div className="text-[9px] text-warn font-bold">НЕ ОБРАБОТАНО</div>
                            </div>
                          )}
                        </div>
                        
                        {/* Badge Tags */}
                        {processed && p.flags && p.flags.includes("silicone") && (
                          <div className="absolute top-1.5 left-1.5 flex flex-wrap gap-1">
                            <div className="w-2 h-2 rounded-full bg-danger animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.8)]" title="Силикон"></div>
                          </div>
                        )}

                        <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-bg-deep via-bg-deep/80 to-transparent p-2.5">
                          <div className="text-[11px] text-white font-mono font-bold">{pDate}</div>
                          <div className="mt-0.5 flex items-center justify-between">
                            <span className="text-[9px] text-muted uppercase tracking-tighter">{pPoseSource}</span>
                            <EvidenceBadge level={processed ? "real" : "pending"} />
                            <span className={`text-[10px] font-bold font-mono ${Math.abs(pYaw ?? 0) < 15 ? 'text-ok' : 'text-info'}`}>
                              {pYaw !== null ? `${pYaw > 0 ? '+' : ''}${pYaw.toFixed(0)}°` : "—"}
                            </span>
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
          
          {filtered.length === 0 && (
            <div className="py-16 text-center rounded-3xl border border-dashed border-line bg-white/5">
              <div className="text-muted text-[12px] uppercase tracking-widest mb-2 font-medium">Нет данных по фильтру</div>
              <button 
                onClick={() => {
                  setSelectedYear("all");
                  setQuery("");
                  setMaxYaw(90);
                }}
                className="text-accent text-[11px] hover:underline"
              >
                Сбросить все параметры
              </button>
            </div>
          )}
        </div>
      </div>

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}

      {opened && (
        <PhotoDetailModal
          photoId={opened.id}
          point={{
            year: opened.year,
            photo: opened.photo,
            photoId: opened.id,
            pose: { yaw: null, pitch: null, classification: "unknown", source: "none" },
            index: 0,
            identity: opened.cluster ?? "не определён",
            anomaly: opened.flags.includes("silicone")
              ? "danger"
              : opened.flags.includes("anomaly")
              ? "warn"
              : undefined,
          }}
          onClose={() => setOpened(null)}
        />
      )}
    </Page>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-muted text-[10px] font-bold uppercase tracking-wider pl-1">{label}</span>
      {children}
    </label>
  );
}

function Select<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: readonly T[] }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white outline-none focus:border-accent transition-colors appearance-none cursor-pointer"
      style={{ backgroundImage: 'url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'white\' stroke-width=\'2\' stroke-linecap=\'round\' stroke-linejoin=\'round\'%3e%3cpolyline points=\'6 9 12 15 18 9\'%3e%3c/polyline%3e%3c/svg%3e")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right 0.75rem center', backgroundSize: '1em' }}
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o === "any" ? "Все" : o === "main" ? "Основные" : o === "myface" ? "Калибровочные" : o.replace(/_/g, " ")}
        </option>
      ))}
    </select>
  );
}

function MiniStat({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="bg-bg-panel border border-line rounded-lg p-2.5">
      <div className="text-xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[10px] text-muted">{label}</div>
    </div>
  );
}
