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
    <Page title="Settings" subtitle="Algorithm thresholds, pipeline toggles, cache">
      <div className="grid grid-cols-2 gap-3">
        <PanelCard title="Expression thresholds">
          <Slider label={`Smile threshold (${smileTh.toFixed(2)})`} value={smileTh} onChange={setSmileTh} />
          <Slider label={`Jaw-open threshold (${jawTh.toFixed(2)})`} value={jawTh} onChange={setJawTh} />
          <Toggle
            label="Exclude soft-tissue zones on smile"
            value={excludeSoftOnSmile}
            onChange={setExcludeSoftOnSmile}
          />
        </PanelCard>

        <PanelCard title="Bayesian priors">
          <Slider
            label={`H1 prior · double / mask (${h1Prior.toFixed(3)})`}
            min={0.001}
            max={0.1}
            step={0.001}
            value={h1Prior}
            onChange={setH1Prior}
          />
          <div className="text-[11px] text-muted mt-2">
            Elevated H1 prior increases sensitivity to synthetic-material detection (recommended for security-critical
            workflows).
          </div>
        </PanelCard>

        <PanelCard title="Pose detection">
          <Toggle
            label="Enable 3DDFA-V3 fallback when primary detector unsure"
            value={useFallback}
            onChange={setUseFallback}
          />
          <div className="text-[11px] text-muted mt-2">
            Adds redundancy for difficult angles / lighting at the cost of extra VRAM.
          </div>
        </PanelCard>

        <PanelCard title="Reconstruction cache">
          <Slider
            label={`Cache size (${cacheSize})`}
            min={1}
            max={64}
            step={1}
            value={cacheSize}
            onChange={(v) => setCacheSize(Math.round(v))}
          />
          <Toggle
            label="Guard against VRAM overflow (pre-check + explicit free)"
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
