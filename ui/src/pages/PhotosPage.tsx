import { useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { PHOTOS, type PhotoRecord } from "../mock/photos";
import PhotoDetailModal from "../components/photo/PhotoDetailModal";
import UploadModal from "../components/upload/UploadModal";
import { useApp } from "../store/appStore";

const POSE_OPTIONS = ["any", "frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right", "none"] as const;
const FOLDER_OPTIONS = ["any", "main", "myface"] as const;
const POSE_SOURCE_OPTIONS = ["any", "hpe", "3ddfa", "none"] as const;

export default function PhotosPage() {
  const [query, setQuery] = useState("");
  const [pose, setPose] = useState<(typeof POSE_OPTIONS)[number]>("any");
  const [folder, setFolder] = useState<(typeof FOLDER_OPTIONS)[number]>("any");
  const [poseSource, setPoseSource] = useState<(typeof POSE_SOURCE_OPTIONS)[number]>("any");
  const [maxYaw, setMaxYaw] = useState(90);
  const [sortBy, setSortBy] = useState<"date" | "yaw" | "id">("date");
  const [opened, setOpened] = useState<PhotoRecord | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const { setPage } = useApp();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = PHOTOS.filter((p) => {
      if (q && !p.id.toLowerCase().includes(q) && !p.date.includes(q)) return false;
      if (pose !== "any" && p.pose !== pose) return false;
      if (folder !== "any" && p.folder !== folder) return false;
      if (poseSource !== "any" && p.poseSource !== poseSource) return false;
      if (p.yaw !== null && Math.abs(p.yaw) > maxYaw) return false;
      return true;
    });
    if (sortBy === "yaw") {
      list = list.slice().sort((a, b) => Math.abs(a.yaw ?? 999) - Math.abs(b.yaw ?? 999));
    } else if (sortBy === "id") {
      list = list.slice().sort((a, b) => a.id.localeCompare(b.id));
    } else {
      list = list.slice().sort((a, b) => (a.date < b.date ? -1 : 1));
    }
    return list;
  }, [query, pose, folder, poseSource, maxYaw, sortBy]);

  return (
    <Page
      title="Photos"
      subtitle={`${PHOTOS.length} total · ${filtered.length} in view`}
      actions={
        <>
          <button
            onClick={() => setShowUpload(true)}
            className="px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white"
          >
            + Upload
          </button>
          <button
            onClick={() => setPage("jobs")}
            className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white"
          >
            Go to jobs
          </button>
        </>
      }
    >
      <PanelCard title="Filters" className="mb-3">
        <div className="grid grid-cols-6 gap-2 text-[11px]">
          <Field label="Search id / date">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="2012-07 or main-…"
              className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-white"
            />
          </Field>
          <Field label="Folder (real)">
            <Select value={folder} onChange={setFolder as any} options={FOLDER_OPTIONS} />
          </Field>
          <Field label="Pose (real)">
            <Select value={pose} onChange={setPose as any} options={POSE_OPTIONS} />
          </Field>
          <Field label="Pose source (real)">
            <Select value={poseSource} onChange={setPoseSource as any} options={POSE_SOURCE_OPTIONS} />
          </Field>
          <Field label={`Max |yaw| ≤ ${maxYaw}° (real)`}>
            <input
              type="range"
              min={0}
              max={90}
              step={1}
              value={maxYaw}
              onChange={(e) => setMaxYaw(+e.target.value)}
              className="w-full"
            />
          </Field>
        </div>
        <div className="flex items-center gap-2 mt-2 text-[11px]">
          <span className="text-muted">Sort:</span>
          {(["date", "yaw", "id"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setSortBy(s)}
              className={`px-2 h-6 rounded ${sortBy === s ? "bg-line text-white" : "bg-bg-deep text-muted hover:text-white"}`}
            >
              {s}
            </button>
          ))}
        </div>
      </PanelCard>

      <div className="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-2">
        {filtered.slice(0, 500).map((p) => (
          <button
            key={p.id}
            onClick={() => setOpened(p)}
            className="relative group rounded overflow-hidden border border-line hover:border-info bg-bg-deep text-left"
          >
            <img src={p.photo} alt={p.id} className="w-full aspect-square object-cover" loading="lazy" />
            <div className="absolute top-1 left-1 flex flex-wrap gap-0.5 max-w-[calc(100%-8px)]">
              {p.flags.slice(0, 3).map((f) => (
                <span
                  key={f}
                  className={`text-[8px] px-1 rounded ${
                    f === "silicone" || f === "anomaly"
                      ? "bg-danger/80 text-white"
                      : f === "chrono"
                      ? "bg-warn/80 text-black"
                      : f === "cluster_b"
                      ? "bg-accent/80 text-white"
                      : "bg-line/80 text-white"
                  }`}
                >
                  {f}
                </span>
              ))}
            </div>
            <div className="absolute bottom-0 inset-x-0 bg-gradient-to-t from-black/90 to-transparent p-1">
              <div className="text-[10px] text-white font-mono truncate">{p.date || p.id.replace(/^myface-|^main-/, "")}</div>
              <div className="text-[9px] text-muted flex justify-between">
                <span>{p.pose}</span>
                <span className="font-mono text-info">
                  {p.yaw !== null ? `${p.yaw.toFixed(0)}°` : "—"} · {p.poseSource}
                </span>
              </div>
            </div>
          </button>
        ))}
      </div>

      {filtered.length > 500 && (
        <div className="text-[11px] text-muted mt-3 text-center">
          Showing first 500 of {filtered.length}. Refine filters to see more.
        </div>
      )}

      {showUpload && <UploadModal onClose={() => setShowUpload(false)} />}

      {opened && (
        <PhotoDetailModal
          photoId={opened.id}
          point={{
            year: opened.year,
            photo: opened.photo,
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
    <label className="flex flex-col gap-1">
      <span className="text-muted">{label}</span>
      {children}
    </label>
  );
}

function Select<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: readonly T[] }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-white"
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}
