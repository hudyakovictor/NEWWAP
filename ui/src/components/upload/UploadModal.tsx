import { useCallback, useState } from "react";
import Modal from "../common/Modal";
import { api } from "../../api";

interface Queued {
  file: File;
  preview: string;
  status: "queued" | "uploading" | "done" | "failed";
}

export default function UploadModal({ onClose }: { onClose: () => void }) {
  const [items, setItems] = useState<Queued[]>([]);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<{ accepted: number; rejected: number; jobId: string } | null>(null);

  const handleFiles = useCallback((files: FileList | File[]) => {
    const list: Queued[] = Array.from(files)
      .filter((f) => f.type.startsWith("image/"))
      .map((f) => ({
        file: f,
        preview: URL.createObjectURL(f),
        status: "queued",
      }));
    setItems((prev) => [...prev, ...list]);
  }, []);

  async function submit() {
    if (!items.length) return;
    setBusy(true);
    setItems((prev) => prev.map((x) => ({ ...x, status: "uploading" })));
    const res = await api.uploadPhotos(items.map((x) => x.file));
    setItems((prev) => prev.map((x) => ({ ...x, status: "done" })));
    setReport(res);
    setBusy(false);
  }

  return (
    <Modal title="Upload photos" onClose={onClose} width="max-w-4xl">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          handleFiles(e.dataTransfer.files);
        }}
        className={`border-2 border-dashed rounded-lg p-6 text-center ${
          drag ? "border-info bg-info/10" : "border-line"
        }`}
      >
        <div className="text-[12px] text-white mb-2">Drop images here or click to select</div>
        <input
          type="file"
          multiple
          accept="image/*"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
          className="block mx-auto text-[11px] text-muted"
        />
        <div className="text-[10px] text-muted mt-2">
          Supports JPG / PNG. Files are processed through the 3DDFA_v3 pipeline after upload.
        </div>
      </div>

      {items.length > 0 && (
        <div className="mt-4">
          <div className="text-[11px] text-muted mb-2">{items.length} file(s) queued</div>
          <div className="grid grid-cols-6 gap-2 max-h-72 overflow-auto">
            {items.map((it, i) => (
              <div key={i} className="relative bg-bg-deep rounded border border-line/60 overflow-hidden">
                <img src={it.preview} alt="" className="w-full aspect-square object-cover" />
                <div className="absolute top-1 left-1 text-[9px] px-1 rounded bg-bg/70 text-white truncate max-w-[calc(100%-8px)]">
                  {it.file.name}
                </div>
                <div
                  className={`absolute bottom-1 left-1 text-[9px] px-1 rounded ${
                    it.status === "done"
                      ? "bg-ok/60 text-white"
                      : it.status === "uploading"
                      ? "bg-info/60 text-white"
                      : it.status === "failed"
                      ? "bg-danger/60 text-white"
                      : "bg-line/80 text-muted"
                  }`}
                >
                  {it.status}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {report && (
        <div className="mt-3 text-[11px] p-2 rounded bg-ok/20 text-ok">
          ✓ Upload complete: {report.accepted} accepted, {report.rejected} rejected. Extract job <span className="font-mono">{report.jobId}</span> started.
        </div>
      )}

      <div className="flex justify-end gap-2 mt-4">
        <button onClick={onClose} className="px-3 h-8 rounded bg-line text-[11px] text-white">
          Close
        </button>
        <button
          onClick={submit}
          disabled={!items.length || busy}
          className="px-3 h-8 rounded bg-accent/80 hover:bg-accent disabled:opacity-40 text-[11px] text-white"
        >
          {busy ? "Uploading…" : `Ingest ${items.length} photo(s)`}
        </button>
      </div>
    </Modal>
  );
}
