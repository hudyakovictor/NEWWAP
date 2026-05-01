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

const tabs = [
  { id: "overview", label: "Обзор" },
  { id: "reconstruction", label: "3D-реконструкция" },
  { id: "zones", label: "21 зона" },
  { id: "texture", label: "Текстура и синтетика" },
  { id: "pose", label: "Поза и выражение" },
  { id: "chronology", label: "Хронология" },
  { id: "calibration", label: "Калибровка" },
  { id: "similar", label: "Похожие фото" },
  { id: "audit_trail", label: "Аудит-след" },
  { id: "meta", label: "Метаданные" },
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
  const effectiveYear = propYear || point?.year || null;
  const effectiveIdentity = point?.identity ?? null;
  
  const [currentPhotoId, setCurrentPhotoId] = useState<string>(effectivePhotoUrl);

  useEffect(() => {
    setCurrentPhotoId(effectivePhotoUrl);
  }, [effectivePhotoUrl]);

  const detail = useMemo(() => buildPhotoDetail(effectiveYear, currentPhotoId), [effectiveYear, currentPhotoId]);
  const [tab, setTab] = useState<TabId>("overview");
  const [hoveredZone, setHoveredZone] = useState<string | undefined>();
  const { openPairWith } = useApp();

  const yearPhotos = useMemo(() => {
    if (effectiveYear == null) return [];
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
                {detail.year} · {detail.meta.resolution ?? "нет данных"} · {detail.meta.source ?? "нет данных"} · кластер{" "}
                <span className={effectiveIdentity === "A" ? "text-accent" : effectiveIdentity === "B" ? "text-danger" : "text-muted"}>
                  {effectiveIdentity ?? "нет данных"}
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
                  title="Установить как фото A в анализе пары"
                >
                  Сравнить как A
                </button>
                <button
                  onClick={() => compare("B")}
                  className="px-2 h-7 text-[11px] rounded bg-accent/70 hover:bg-accent text-white mr-2"
                  title="Установить как фото B в анализе пары"
                >
                  Сравнить как B
                </button>
              </>
            )}
            {onPrev && (
              <button
                onClick={onPrev}
                className="w-7 h-7 rounded bg-line/60 hover:bg-line text-white"
                title="Предыдущий год"
              >
                ‹
              </button>
            )}
            {onNext && (
              <button
                onClick={onNext}
                className="w-7 h-7 rounded bg-line/60 hover:bg-line text-white"
                title="Следующий год"
              >
                ›
              </button>
            )}
            <button
              onClick={onClose}
              className="w-7 h-7 rounded bg-danger/30 hover:bg-danger/60 text-white ml-2"
              title="Закрыть"
            >
              ×
            </button>
          </div>
        </div>

        {/* YEAR GALLERY */}
        {yearPhotos.length > 1 && (
          <div className="flex items-center gap-2 px-4 py-2 bg-bg-deep/50 overflow-x-auto scrollbar-thin border-b border-line/40 shrink-0">
            <span className="text-[10px] uppercase text-muted tracking-widest shrink-0 mr-2">Все фото {effectiveYear ?? "????"} ({yearPhotos.length}):</span>
            <div className="flex gap-1">
              {yearPhotos.map(p => {
                const isActive = currentPhotoId.includes(p.id) || currentPhotoId === p.url;
                return (
                  <button 
                    key={p.id}
                    onClick={() => setCurrentPhotoId(p.url)}
                    title={`${p.date || 'Дата неизвестна'} — ${p.pose.classification}`}
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

function Bar({ label, value, color = "#22c55e", max = 1 }: { label: string; value: number | null; color?: string; max?: number }) {
  if (value == null) {
    return (
      <div className="flex items-center gap-2">
        <div className="text-[11px] text-muted w-40 truncate">{label}</div>
        <div className="flex-1 h-2 bg-bg rounded overflow-hidden">
          <div className="h-full bg-line/20" style={{ width: "100%" }} />
        </div>
        <div className="text-[11px] font-mono w-14 text-right text-muted">—</div>
      </div>
    );
  }
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
  identity: "A" | "B" | string | null;
}) {
  return (
    <div className="grid grid-cols-12 gap-3 h-full">
      <div className="col-span-3">
        <FaceZoneMap photo={detail.photo} zones={detail.zones} hovered={hovered} onHover={onHover} />
      </div>

      <div className="col-span-4 flex flex-col gap-3">
        <Panel title="Байесовский вердикт">
          <Bar label="H0 — тот же человек" value={detail.bayes.H0} color="#22c55e" />
          <div className="mt-1">
            <Bar label="H1 — двойник / маска" value={detail.bayes.H1} color="#ef4444" />
          </div>
          <div className="mt-1">
            <Bar label="H2 — другой человек" value={detail.bayes.H2} color="#f59e0b" />
          </div>
          <div className="text-[10px] text-muted mt-2">
            Кластер идентичности:{" "}
            <span className={identity === "A" ? "text-accent" : identity === "B" ? "text-danger" : "text-muted"}>{identity ?? "нет данных"}</span>
          </div>
        </Panel>
        <Panel title="Детектор синтетических материалов">
          <Bar label="Синтетическая вероятность" value={detail.texture.syntheticProb} color="#ef4444" />
          <div className="mt-1">
            <Bar label="Аномалия FFT" value={detail.texture.fftAnomaly} color="#f59e0b" />
          </div>
          <div className="mt-1">
            <Bar label="Спекулярный (блик)" value={detail.texture.specularIndex} color="#38bdf8" />
          </div>
          <div className="mt-1">
            <Bar label="Здоровье альбедо" value={detail.texture.albedoHealth} color="#22c55e" />
          </div>
        </Panel>
      </div>

      <div className="col-span-5 flex flex-col gap-3">
        <Panel title="Поза и выражение">
          <div className="grid grid-cols-4 gap-2">
            <Stat label="рыскан." value={`${detail.pose.yaw}°`} />
            <Stat label="тангаж" value={`${detail.pose.pitch}°`} />
            <Stat label="крен" value={`${detail.pose.roll}°`} />
            <Stat label="довер." value={detail.pose.confidence != null ? detail.pose.confidence.toFixed(2) : "—"} />
            <Stat label="класс" value={detail.pose.classification} small />
            <Stat label="улыбка" value={detail.expression.smile != null ? detail.expression.smile.toFixed(2) : "—"} />
            <Stat label="челюсть" value={detail.expression.jawOpen != null ? detail.expression.jawOpen.toFixed(2) : "—"} />
            <Stat label="нейтр." value={detail.expression.neutral ? "да" : "нет"} />
          </div>
          {detail.pose.fallback && (
            <div className="text-[10px] text-warn mt-2">
              ⓘ Низкая уверенность основного детектора позы — переключение на 3DDFA-V3.
            </div>
          )}
        </Panel>
        <Panel title="Хронологические флаги">
          <div className="text-[11px] space-y-1">
            <div className="text-muted">
              Δt = {detail.chronology.prevDelta}г · скачок костной асимметрии:{" "}
              <span className="font-mono text-white">{detail.chronology.boneAsymmetryJump}</span> · скачок связок:{" "}
              <span className="font-mono text-white">{detail.chronology.ligamentJump}</span>
            </div>
            {(detail.chronology.flags ?? []).length === 0 && (
              <div className="text-ok">Хронологических несоответствий не обнаружено.</div>
            )}
            {(detail.chronology.flags ?? []).map((f, i) => (
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
        <Panel title="Заметки">
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
    { title: "Оригинал", src: detail.photo },
    { title: "Наложение лица", src: detail.reconstruction.overlay ?? undefined },
    { title: "Рендер лица", src: detail.reconstruction.renderFace ?? undefined },
    { title: "Геометрия (форма)", src: detail.reconstruction.renderShape ?? undefined },
    { title: "Маска", src: detail.reconstruction.renderMask ?? undefined },
    { title: "UV-текстура", src: detail.reconstruction.uvTexture ?? undefined },
    { title: "UV-уверенность", src: detail.reconstruction.uvConfidence ?? undefined },
    { title: "UV-маска", src: detail.reconstruction.uvMask ?? undefined },
  ];
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-5 flex flex-col gap-3">
        <div className="bg-bg-deep rounded border border-line/60 overflow-hidden" style={{ height: 460 }}>
          <MeshViewer objUrl={detail.reconstruction.meshObj ?? ""} textureUrl={detail.reconstruction.uvTexture ?? undefined} />
        </div>
        <Panel title="Статистика меша">
          <div className="grid grid-cols-2 gap-2">
            <Stat label="вершины" value={(detail.reconstruction.vertices ?? 0).toLocaleString()} />
            <Stat label="треугольники" value={(detail.reconstruction.meshTriangles ?? 0).toLocaleString()} />
            <Stat label="модель" value="3DDFA_v3" />
            <Stat label="нейтр. выр." value={detail.expression.neutral ? "да" : "нет"} />
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
        Поиск ближайших соседей доступен при открытии фото со страницы «Фото».
      </div>
    );
  }

  if (loading) return <div className="text-[11px] text-muted">Ранжирование {`>`} 1 700 фото…</div>;

  return (
    <div>
      <div className="text-[11px] text-muted mb-2">
        Топ-{items.length} ближайших фото по позе + кластеру + синтетическому профилю.
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
                  сравнить
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
  // [FIX-C3] Calculate weighted similarity only over visible (non-excluded) zones
  const visibleZones = detail.zones.filter((z) => !z.excluded);
  const total = visibleZones.reduce((acc, z) => acc + z.weight, 0);
  const weighted = total > 0
    ? visibleZones.reduce((acc, z) => acc + z.weight * (z.score ?? 0), 0) / total
    : 0;

  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-4">
        <FaceZoneMap photo={detail.photo} zones={detail.zones} hovered={hovered} onHover={onHover} />
        <Panel title="Сводка" className="mt-3">
          <Bar label="Взвешенное сходство" value={weighted} color="#22c55e" />
          <div className="text-[10px] text-muted mt-2">
            Костные зоны имеют вес до 1.00; мягкие ткани занижены или динамически исключены (улыбка/челюсть).
          </div>
        </Panel>
      </div>
      <div className="col-span-8 space-y-3">
        {(Object.entries(grouped) as [keyof typeof grouped, typeof detail.zones][]).map(([grp, zs]) => (
          <Panel key={grp} title={`Зоны ${grp} (${zs.length})`}>
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
                        width: `${z.excluded ? 0 : (z.score ?? 0) * 100}%`,
                        background: z.excluded ? "#6b7a90" : "#22c55e",
                      }}
                    />
                  </div>
                  {z.excluded && <span className="text-[9px] text-muted">исключена</span>}
                  {!z.visible && <span className="text-[9px] text-warn">скрыта</span>}
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
  // [FIX-C1] Use real FFT spectrum data from backend if available
  const hasRealFftData = detail.texture.fftSpectrumData && detail.texture.fftSpectrumData.length === 24;
  const bars = hasRealFftData
    ? detail.texture.fftSpectrumData!
    : null; // No fake data - show stub message instead
  return (
    <div className="grid grid-cols-12 gap-3">
      <div className="col-span-5 space-y-3">
        <Panel title="Разбор синтетической вероятности">
          <Bar label="Синтетическая вероятность" value={detail.texture.syntheticProb} color="#ef4444" />
          <div className="mt-1">
            <Bar label="Аномалия FFT" value={detail.texture.fftAnomaly} color="#f59e0b" />
          </div>
          <div className="mt-1">
            <Bar label="Сложность LBP" value={detail.texture.lbpComplexity} color="#a855f7" />
          </div>
          <div className="mt-1">
            <Bar label="Спекулярный индекс" value={detail.texture.specularIndex} color="#38bdf8" />
          </div>
          <div className="mt-1">
            <Bar label="Здоровье альбедо" value={detail.texture.albedoHealth} color="#22c55e" />
          </div>
        </Panel>
        <Panel title="Диагноз">
          <div className="text-[11px] text-muted leading-snug">
            {(detail.texture.syntheticProb ?? 0) > 0.5
              ? "Текстурный паттерн несовместим с естественной кожей. Повышенная FFT-периодичность и спекулярный индекс указывают на возможный силиконовый или латексный протез."
              : "Текстура в пределах естественной вариабельности кожи. Признаков силикона/дипфейка не обнаружено."}
          </div>
        </Panel>
      </div>
      <div className="col-span-7 space-y-3">
        <Panel title="FFT-спектр (радиальный)">
          {hasRealFftData ? (
            <div className="flex items-end h-32 gap-0.5">
              {bars!.map((b, i) => (
                <div
                  key={i}
                  className="flex-1 bg-info/70"
                  style={{ height: `${Math.max(0.05, b) * 100}%` }}
                  title={`freq ${i}: ${b.toFixed(2)}`}
                />
              ))}
            </div>
          ) : (
            <div className="h-32 flex items-center justify-center bg-muted/20 rounded">
              <span className="text-[11px] text-muted">FFT данные недоступны — требуется запуск texture pipeline</span>
            </div>
          )}
          <div className="text-[10px] text-muted mt-2">
            Радиальное распределение энергии по FFT кожных участков. Всплески на высоких частотах указывают на периодические паттерны.
            {!hasRealFftData && " (заглушка — нет реальных данных)"}
          </div>
        </Panel>
        <Panel title="UV-текстура и уверенность">
          <div className="grid grid-cols-2 gap-2">
            <img src={detail.reconstruction.uvTexture ?? undefined} alt="uv" className="w-full rounded bg-black" />
            <img src={detail.reconstruction.uvConfidence ?? undefined} alt="uv conf" className="w-full rounded bg-black" />
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
        <Panel title="Детектор позы">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="рыскан." value={`${detail.pose.yaw}°`} />
            <Stat label="тангаж" value={`${detail.pose.pitch}°`} />
            <Stat label="крен" value={`${detail.pose.roll}°`} />
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <Stat label="класс" value={detail.pose.classification} small />
            <Stat label="уверенность" value={detail.pose.confidence != null ? detail.pose.confidence.toFixed(2) : "—"} />
            <Stat label="запасной" value={detail.pose.fallback ? "3DDFA-V3" : "основной"} small />
          </div>
        </Panel>
        <Panel title="Видимость зон (по позе)">
          <div className="grid grid-cols-2 gap-1 text-[11px]">
            {detail.zones.map((z) => (
              <div key={z.id} className="flex justify-between">
                <span className="text-muted">{z.name}</span>
                <span className={z.visible ? "text-ok" : "text-danger"}>{z.visible ? "видима" : "скрыта"}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>
      <div className="col-span-6 space-y-3">
        <Panel title="Выражение">
          <Bar label="Улыбка" value={detail.expression.smile} color="#f59e0b" />
          <div className="mt-1">
            <Bar label="Челюсть открыта" value={detail.expression.jawOpen} color="#f59e0b" />
          </div>
          <div className="text-[11px] text-muted mt-2">
            Пороги: улыбка ≥ 0.30, челюсть ≥ 0.25. Субъект{" "}
            <span className={detail.expression.neutral ? "text-ok" : "text-warn"}>
              {detail.expression.neutral ? "нейтрален" : "выразителен"}
            </span>.
          </div>
        </Panel>
        <Panel title="Динамически исключённые зоны">
          <div className="flex flex-wrap gap-1">
            {(detail.expression.excludedZones ?? []).length === 0 && (
              <span className="text-[11px] text-ok">Нет — все зоны участвуют.</span>
            )}
            {(detail.expression.excludedZones ?? []).map((id) => (
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
        <Panel title="Межкадровые дельты">
          <KV k="предыдущий кадр" v={detail.chronology.prevYear ?? "—"} />
          <KV k="Δt" v={`${detail.chronology.prevDelta} г`} />
          <KV k="скачок костной асимметрии" v={detail.chronology.boneAsymmetryJump} />
          <KV k="скачок связок" v={detail.chronology.ligamentJump} />
        </Panel>
      </div>
      <div className="col-span-7">
        <Panel title="Поднятые флаги">
          {(detail.chronology.flags ?? []).length === 0 ? (
            <div className="text-[11px] text-ok">Хронологических несоответствий не обнаружено.</div>
          ) : (
            <ul className="space-y-1 text-[11px]">
              {(detail.chronology.flags ?? []).map((f, i) => (
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
        <Panel title="Калибровочный бакет для этого фото">
          <KV k="бакет" v={c.bucket} />
          <KV k="уровень доверия" v={c.level} />
          <KV k="кол-во образцов" v={c.sampleCount} />
          <KV k="дисперсия" v={c.variance} />
        </Panel>
      </div>
      <div className="col-span-6">
        <Panel title="Рантайм-адаптация">
          <div className="text-[11px] text-muted leading-snug">
            {c.level === "high"
              ? "Прямая стратегия: стандартные пороги."
              : c.level === "medium"
              ? "Консервативная стратегия: расширенные доверительные интервалы."
              : c.level === "low"
              ? "Бакет с низкой уверенностью — запасной вес смещён к сравнению только по костям."
              : "Ненадёжный бакет — исключён из рантайм-сравнений до повторной калибровки."}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function AuditTrailTab({ year, photoId }: { year: number | null; photoId?: string }) {
  const [items, setItems] = useState<LogEntry[]>([]);
  const [showAllLevels, setShowAllLevels] = useState(false);

  useEffect(() => {
    const filterAndSet = () => {
      const yearStr = year != null ? String(year) : "";
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
          {visible.length} запис{visible.length === 1 ? "ь" : visible.length < 5 ? "и" : "ей"}, затрагивающ{" "}
          <span className="text-white font-mono">год={year}</span>
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
          показывать trace/debug
        </label>
      </div>

      {visible.length === 0 ? (
        <div className="text-[11px] text-muted bg-bg-deep/50 border border-line/60 rounded p-3">
          Нет записей лога, ссылающихся на это фото или год. Взаимодействуйте с ним
          (откройте детали, смените пару, запустите аудит), чтобы заполнить след.
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
                      <div className="text-muted">ожидается {v.expected}</div>
                      <div className="text-warn">фактически {JSON.stringify(v.actual)}</div>
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
        <Panel title="Файл">
          <KV k="id фото" v={detail.meta.id} />
          <KV k="имя файла" v={detail.meta.filename} />
          <KV k="снято" v={detail.meta.capturedAt} />
          <KV k="источник" v={detail.meta.source} />
          <KV k="разрешение" v={detail.meta.resolution} />
          <KV k="размер" v={`${detail.meta.sizeKB} КБ`} />
          <KV k="md5" v={detail.meta.md5} />
        </Panel>
      </div>
      <div className="col-span-6">
        <Panel title="Кэш пайплайна">
          <KV k="reconstruction_v1.pkl" v="в кэше" />
          <KV k="нейтральный вариант" v={detail.expression.neutral ? "есть" : "нужен"} />
          <KV k="занимает VRAM" v="~180 МБ" />
          <KV k="последнее обновление" v={`${detail.year}-01-01 · smoke-test`} />
        </Panel>
      </div>
    </div>
  );
}
