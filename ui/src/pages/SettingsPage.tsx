import { useState } from "react";
import { Page, PanelCard } from "../components/common/Page";

export default function SettingsPage() {
  const [smileTh, setSmileTh] = useState(0.3);
  const [jawTh, setJawTh] = useState(0.25);
  const [h1Prior, setH1Prior] = useState(0.02);
  const [cacheSize, setCacheSize] = useState(10);
  const [useFallback, setUseFallback] = useState(true);
  const [excludeSoftOnSmile, setExcludeSoftOnSmile] = useState(true);
  const [vramGuard, setVramGuard] = useState(true);

  return (
    <Page title="Настройки" subtitle="Пороги алгоритмов, переключатели конвейера, кэш">
      <div className="grid grid-cols-2 gap-3">
        <PanelCard title="Пороги мимики">
          <Slider label={`Порог улыбки (${smileTh.toFixed(2)})`} value={smileTh} onChange={setSmileTh} />
          <Slider label={`Порог раскрытия челюсти (${jawTh.toFixed(2)})`} value={jawTh} onChange={setJawTh} />
          <Toggle
            label="Исключать зоны мягких тканей при улыбке"
            value={excludeSoftOnSmile}
            onChange={setExcludeSoftOnSmile}
          />
        </PanelCard>

        <PanelCard title="Байесовские априори">
          <Slider
            label={`H1 prior · double / mask (${h1Prior.toFixed(3)})`}
            min={0.001}
            max={0.1}
            step={0.001}
            value={h1Prior}
            onChange={setH1Prior}
          />
          <div className="text-[11px] text-muted mt-2">
            Повышенный априори H1 увеличивает чувствительность к обнаружению синтетики (рекомендуется для критичных с точки зрения безопасности рабочих процессов).
          </div>
        </PanelCard>

        <PanelCard title="Детекция ракурса">
          <Toggle
            label="Включить запасной 3DDFA-V3, если основной детектор не уверен"
            value={useFallback}
            onChange={setUseFallback}
          />
          <div className="text-[11px] text-muted mt-2">
            Добавляет избыточность для сложных ракурсов / освещения ценой дополнительного VRAM.
          </div>
        </PanelCard>

        <PanelCard title="Кэш реконструкций">
          <Slider
            label={`Размер кэша (${cacheSize})`}
            min={1}
            max={64}
            step={1}
            value={cacheSize}
            onChange={(v) => setCacheSize(Math.round(v))}
          />
          <Toggle
            label="Защита от переполнения VRAM (предпроверка + явное освобождение)"
            value={vramGuard}
            onChange={setVramGuard}
          />
        </PanelCard>
      </div>
    </Page>
  );
}

function Slider({
  label,
  value,
  onChange,
  min = 0,
  max = 1,
  step = 0.01,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <label className="flex flex-col gap-1 my-2">
      <span className="text-[11px] text-muted">{label}</span>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(+e.target.value)}
        className="w-full"
      />
    </label>
  );
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 my-2 cursor-pointer">
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
      <span className="text-[11px] text-white">{label}</span>
    </label>
  );
}
