import { useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { PHOTOS, type PhotoRecord } from "../mock/photos";
import PhotoDetailModal from "../components/photo/PhotoDetailModal";
import UploadModal from "../components/upload/UploadModal";
import { useApp } from "../store/appStore";

const POSE_GROUPS = ["frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right", "none"] as const;
const FOLDER_OPTIONS = ["any", "main", "myface"] as const;
const POSE_SOURCE_OPTIONS = ["any", "hpe", "3ddfa", "none"] as const;

export default function PhotosPage() {
  const [query, setQuery] = useState("");
  const [selectedYear, setSelectedYear] = useState<number | "all">("any" as any); // Use "any" for all
  const [folder, setFolder] = useState<(typeof FOLDER_OPTIONS)[number]>("main");
  const [poseSource, setPoseSource] = useState<(typeof POSE_SOURCE_OPTIONS)[number]>("any");
  const [maxYaw, setMaxYaw] = useState(90);
  const [opened, setOpened] = useState<PhotoRecord | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const { setPage } = useApp();

  // Get available years from data
  const availableYears = useMemo(() => {
    const years = Array.from(new Set(PHOTOS.map(p => p.year).filter(y => y > 0))).sort((a, b) => a - b);
    return years;
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return PHOTOS.filter((p) => {
      if (q && !p.id.toLowerCase().includes(q) && !p.date.includes(q)) return false;
      if (selectedYear !== ("any" as any) && p.year !== selectedYear) return false;
      if (folder !== "any" && p.folder !== folder) return false;
      if (poseSource !== "any" && p.poseSource !== poseSource) return false;
      if (p.yaw !== null && Math.abs(p.yaw) > maxYaw) return false;
      return true;
    });
  }, [query, selectedYear, folder, poseSource, maxYaw]);

  const grouped = useMemo(() => {
    const groups: Record<string, PhotoRecord[]> = {};
    POSE_GROUPS.forEach(g => groups[g] = []);
    
    filtered.forEach(p => {
      const g = p.pose || "none";
      if (!groups[g]) groups[g] = [];
      groups[g].push(p);
    });

    // Sort each group by year/date
    Object.keys(groups).forEach(g => {
      groups[g].sort((a, b) => (a.date || "") < (b.date || "") ? -1 : 1);
    });

    return groups;
  }, [filtered]);

  return (
    <Page
      title="Dataset Inspector"
      subtitle={`${PHOTOS.length} total · ${filtered.length} filtered by chronology & angle`}
      actions={
        <div className="flex gap-2">
          <button
            onClick={() => setShowUpload(true)}
            className="px-4 h-9 rounded-full bg-white/10 hover:bg-white/20 transition-all text-[12px] font-medium text-white border border-white/10"
          >
            + Import Assets
          </button>
          <button
            onClick={() => setPage("jobs")}
            className="px-4 h-9 rounded-full bg-accent/80 hover:bg-accent transition-all text-[12px] font-medium text-white shadow-lg shadow-accent/20"
          >
            Pipeline Status
          </button>
        </div>
      }
    >
      {/* Year Selection Timeline */}
      <div className="mb-6 p-4 rounded-2xl bg-bg-deep/50 border border-line/50 backdrop-blur-md">
        <div className="flex items-center justify-between mb-3 px-1">
          <span className="text-[11px] font-bold uppercase tracking-wider text-muted/80">Chronology Filter</span>
          <span className="text-[11px] font-mono text-info bg-info/10 px-2 py-0.5 rounded-full">
            {selectedYear === ("any" as any) ? "All Years" : `Year: ${selectedYear}`}
          </span>
        </div>
        <div className="flex gap-1 overflow-x-auto pb-2 scrollbar-none no-scrollbar">
          <button
            onClick={() => setSelectedYear("any" as any)}
            className={`flex-shrink-0 px-3 py-1.5 rounded-lg text-[11px] font-mono transition-all ${
              selectedYear === ("any" as any) 
                ? "bg-accent text-white shadow-md shadow-accent/20" 
                : "bg-bg-deep text-muted hover:text-white border border-white/5"
            }`}
          >
            ANY
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

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="md:col-span-1">
          <PanelCard title="Metadata Filters" className="h-full">
            <div className="flex flex-col gap-4 text-[11px]">
              <Field label="Text Search">
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="ID or Date..."
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line focus:border-accent transition-colors text-white outline-none"
                />
              </Field>
              <Field label="Data Partition">
                <Select value={folder} onChange={setFolder as any} options={FOLDER_OPTIONS} />
              </Field>
              <Field label="Detection Source">
                <Select value={poseSource} onChange={setPoseSource as any} options={POSE_SOURCE_OPTIONS} />
              </Field>
              <Field label={`Angle Threshold: |yaw| ≤ ${maxYaw}°`}>
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
                    <span>Frontal</span>
                    <span>Profile</span>
                  </div>
                </div>
              </Field>
            </div>
          </PanelCard>
        </div>

        <div className="md:col-span-3 space-y-8">
          {POSE_GROUPS.map(group => {
            const items = grouped[group] || [];
            if (items.length === 0) return null;

            return (
              <div key={group} className="relative">
                <div className="flex items-center gap-3 mb-4">
                  <h3 className="text-[12px] font-bold text-white uppercase tracking-[0.2em] bg-bg-deep px-3 py-1 rounded-full border border-line shadow-sm">
                    {group.replace(/_/g, " ")}
                  </h3>
                  <div className="h-px flex-1 bg-gradient-to-r from-line to-transparent"></div>
                  <span className="text-[10px] font-mono text-muted">{items.length} units</span>
                </div>
                
                <div className="flex gap-3 overflow-x-auto pb-4 scrollbar-thin scrollbar-thumb-white/10 hover:scrollbar-thumb-white/20 transition-all">
                  {items.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => setOpened(p)}
                      className="flex-shrink-0 w-[160px] relative group rounded-2xl overflow-hidden border border-line/50 hover:border-accent/50 bg-bg-deep text-left transition-all hover:translate-y-[-2px] hover:shadow-xl hover:shadow-accent/10"
                    >
                      <div className="aspect-[3/4] overflow-hidden">
                        <img 
                          src={p.photo} 
                          alt={p.id} 
                          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110" 
                          loading="lazy" 
                        />
                      </div>
                      
                      {/* Badge Tags */}
                      <div className="absolute top-2 left-2 flex flex-wrap gap-1">
                        {p.flags.includes("silicone") && (
                          <div className="w-2 h-2 rounded-full bg-danger animate-pulse shadow-[0_0_8px_rgba(239,68,68,0.8)]" title="Silicone Match"></div>
                        )}
                        {p.flags.includes("anomaly") && (
                          <div className="w-2 h-2 rounded-full bg-warn" title="Anomaly Detected"></div>
                        )}
                      </div>

                      <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-bg-deep via-bg-deep/80 to-transparent p-3">
                        <div className="text-[11px] text-white font-mono font-bold">{p.date || "Unknown Date"}</div>
                        <div className="mt-1 flex items-center justify-between">
                          <span className="text-[9px] text-muted uppercase tracking-tighter">{p.poseSource}</span>
                          <span className={`text-[10px] font-bold font-mono ${Math.abs(p.yaw ?? 0) < 15 ? 'text-success' : 'text-info'}`}>
                            {p.yaw !== null ? `${p.yaw > 0 ? '+' : ''}${p.yaw.toFixed(0)}°` : "—"}
                          </span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            );
          })}
          
          {filtered.length === 0 && (
            <div className="py-20 text-center rounded-3xl border border-dashed border-line bg-white/5">
              <div className="text-muted text-[12px] uppercase tracking-widest mb-2 font-medium">No Data Matching Filters</div>
              <button 
                onClick={() => {
                  setSelectedYear("any" as any);
                  setQuery("");
                  setMaxYaw(90);
                }}
                className="text-accent text-[11px] hover:underline"
              >
                Reset all parameters
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
            identity: opened.cluster,
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
          {o.replace(/_/g, " ")}
        </option>
      ))}
    </select>
  );
}
