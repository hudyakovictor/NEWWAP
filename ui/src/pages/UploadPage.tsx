import { useState, useCallback, useEffect } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api } from "../api";
import { useApp } from "../store/appStore";

interface QueuedPhoto {
  id: string;
  file: File;
  preview: string;
  status: "queued" | "detecting" | "ready" | "uploading" | "done" | "failed";
  date?: string;
  pose?: string;
  dataset?: "main" | "calibration";
}

export default function UploadPage() {
  const { setPage } = useApp();
  const [queued, setQueued] = useState<QueuedPhoto[]>([]);
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [mainDatasetLoading, setMainDatasetLoading] = useState(false);
  const [calibDatasetLoading, setCalibDatasetLoading] = useState(false);

  const handleFiles = useCallback((files: FileList | File[], dataset: "main" | "calibration" = "main") => {
    const list: QueuedPhoto[] = Array.from(files)
      .filter((f) => f.type.startsWith("image/"))
      .map((f) => ({
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        file: f,
        preview: URL.createObjectURL(f),
        status: "queued" as const,
        dataset,
      }));
    setQueued((prev) => [...prev, ...list]);
  }, []);

  // Simulate date and pose detection
  useEffect(() => {
    const detectInterval = setInterval(() => {
      setQueued((prev) =>
        prev.map((p) => {
          if (p.status === "queued") {
            // Simulate detection delay
            setTimeout(() => {
              setQueued((current) =>
                current.map((item) =>
                  item.id === p.id
                    ? {
                        ...item,
                        status: "detecting",
                      }
                    : item
                )
              );
            }, 100);

            // Simulate detection completion
            setTimeout(() => {
              setQueued((current) =>
                current.map((item) => {
                  if (item.id === p.id) {
                    // Extract date from filename
                    const dateMatch = item.file.name.match(/(\d{4})/);
                    const year = dateMatch ? parseInt(dateMatch[1]) : new Date().getFullYear();
                    const date = `${year}-01-01`;

                    // Random pose assignment
                    const poses = ["frontal", "three_quarter_left", "three_quarter_right", "profile_left", "profile_right"];
                    const pose = poses[Math.floor(Math.random() * poses.length)];

                    return {
                      ...item,
                      status: "ready",
                      date,
                      pose,
                    };
                  }
                  return item;
                })
              );
            }, 1500 + Math.random() * 1000);
          }
          return p;
        })
      );
    }, 500);

    return () => clearInterval(detectInterval);
  }, []);

  const uploadMainDataset = async () => {
    setMainDatasetLoading(true);
    try {
      // Use directory picker to select the dataset folder
      const dirHandle = await (window as any).showDirectoryPicker();
      const files: File[] = [];

      for await (const entry of dirHandle.values()) {
        if (entry.kind === 'file') {
          const file = await entry.getFile();
          if (file.type.startsWith('image/')) {
            files.push(file);
          }
        }
      }

      if (files.length === 0) {
        alert("В выбранной директории не найдено изображений");
        return;
      }

      // Add files to queue
      const newItems: QueuedPhoto[] = files.map((f) => ({
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        file: f,
        preview: URL.createObjectURL(f),
        status: "queued" as const,
        dataset: "main",
      }));

      setQueued((prev) => [...prev, ...newItems]);
      alert(`Найдено ${files.length} изображений. Добавлено в очередь загрузки.`);
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // User cancelled the picker
        return;
      }
      console.error("Directory picker failed:", error);
      alert("Не удалось выбрать директорию. Убедитесь, что ваш браузер поддерживает File System Access API.");
    } finally {
      setMainDatasetLoading(false);
    }
  };

  const uploadCalibDataset = async () => {
    setCalibDatasetLoading(true);
    try {
      // Use directory picker to select the calibration folder
      const dirHandle = await (window as any).showDirectoryPicker();
      const files: File[] = [];

      for await (const entry of dirHandle.values()) {
        if (entry.kind === 'file') {
          const file = await entry.getFile();
          if (file.type.startsWith('image/')) {
            files.push(file);
          }
        }
      }

      if (files.length === 0) {
        alert("В выбранной директории не найдено изображений");
        return;
      }

      // Add files to queue with calibration dataset
      const newItems: QueuedPhoto[] = files.map((f) => ({
        id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        file: f,
        preview: URL.createObjectURL(f),
        status: "queued" as const,
        dataset: "calibration",
      }));

      setQueued((prev) => [...prev, ...newItems]);
      alert(`Найдено ${files.length} изображений. Добавлено в очередь загрузки как калибровочные.`);
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // User cancelled the picker
        return;
      }
      console.error("Directory picker failed:", error);
      alert("Не удалось выбрать директорию. Убедитесь, что ваш браузер поддерживает File System Access API.");
    } finally {
      setCalibDatasetLoading(false);
    }
  };

  const uploadQueued = async () => {
    const readyPhotos = queued.filter((p) => p.status === "ready");
    if (readyPhotos.length === 0) return;

    setUploading(true);
    setQueued((prev) =>
      prev.map((p) => (p.status === "ready" ? { ...p, status: "uploading" } : p))
    );

    try {
      // Separate by dataset
      const mainPhotos = readyPhotos.filter((p) => p.dataset === "main");
      const calibPhotos = readyPhotos.filter((p) => p.dataset === "calibration");

      let totalAccepted = 0;
      let totalRejected = 0;
      let jobId = "";

      // Upload main dataset photos
      if (mainPhotos.length > 0) {
        const mainResult = await api.uploadPhotos(mainPhotos.map((p) => p.file));
        totalAccepted += mainResult.accepted;
        totalRejected += mainResult.rejected;
        jobId = mainResult.jobId;
      }

      // Upload calibration dataset photos
      if (calibPhotos.length > 0) {
        const calibResult = await api.uploadPhotos(calibPhotos.map((p) => p.file));
        totalAccepted += calibResult.accepted;
        totalRejected += calibResult.rejected;
        if (!jobId) jobId = calibResult.jobId;
      }

      setQueued((prev) =>
        prev.map((p) =>
          p.status === "uploading" ? { ...p, status: "done" } : p
        )
      );

      // Remove uploaded photos from queue after a delay
      setTimeout(() => {
        setQueued((prev) => prev.filter((p) => p.status !== "done"));
      }, 2000);

      alert(
        `Загрузка завершена: ${totalAccepted} фото принято, ${totalRejected} отклонено. ` +
        `Основной: ${mainPhotos.length}, Калибровка: ${calibPhotos.length}. ` +
        `Задача ${jobId} запущена.`
      );
    } catch (error) {
      console.error("Upload failed:", error);
      setQueued((prev) =>
        prev.map((p) =>
          p.status === "uploading" ? { ...p, status: "failed" } : p
        )
      );
      alert("Ошибка загрузки фото");
    } finally {
      setUploading(false);
    }
  };

  const removePhoto = (id: string) => {
    setQueued((prev) => prev.filter((p) => p.id !== id));
  };

  const clearQueue = () => {
    setQueued([]);
  };

  return (
    <Page
      title="Загрузка фото"
      subtitle="Добавьте фото в анализ или загрузите готовые датасеты"
      actions={
        <div className="flex gap-2">
          <button
            onClick={() => setPage("photos")}
            className="px-4 h-9 rounded-full bg-white/10 hover:bg-white/20 transition-all text-[12px] font-medium text-white border border-white/10"
          >
            К фотоархиву
          </button>
        </div>
      }
    >
      {/* Dataset Upload Section */}
      <div className="mb-6">
        <PanelCard title="Загрузка датасетов из директорий" className="mb-4">
          <div className="text-[11px] text-muted mb-3">
            Выберите директории с фото для загрузки. Система автоматически найдет все изображения и добавит их в очередь.
          </div>
          <div className="grid grid-cols-2 gap-4">
            <button
              onClick={uploadMainDataset}
              disabled={mainDatasetLoading}
              className="p-4 rounded-xl bg-accent/10 hover:bg-accent/20 border border-accent/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="text-[12px] font-bold text-accent mb-1">
                Основной датасет
              </div>
              <div className="text-[10px] text-muted">
                Выбрать директорию с фото
              </div>
              {mainDatasetLoading && (
                <div className="mt-2 text-[10px] text-accent">Загрузка...</div>
              )}
            </button>

            <button
              onClick={uploadCalibDataset}
              disabled={calibDatasetLoading}
              className="p-4 rounded-xl bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="text-[12px] font-bold text-purple-400 mb-1">
                Калибровочный датасет
              </div>
              <div className="text-[10px] text-muted">
                Выбрать директорию с фото
              </div>
              {calibDatasetLoading && (
                <div className="mt-2 text-[10px] text-purple-400">Загрузка...</div>
              )}
            </button>
          </div>
        </PanelCard>
      </div>

      {/* Individual Photo Upload */}
      <PanelCard title="Загрузка отдельных фото" className="mb-4">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            handleFiles(e.dataTransfer.files, "main");
          }}
          className={`border-2 border-dashed rounded-lg p-8 text-center transition-all ${
            drag ? "border-info bg-info/10" : "border-line hover:border-line/60"
          }`}
        >
          <div className="text-[12px] text-white mb-2">
            Перетащите изображения или нажмите для выбора
          </div>
          <input
            type="file"
            multiple
            accept="image/*"
            onChange={(e) => e.target.files && handleFiles(e.target.files, "main")}
            className="block mx-auto text-[11px] text-muted"
          />
          <div className="text-[10px] text-muted mt-2">
            Поддерживаются JPG / PNG. После загрузки фото появится на таймлайне черно-белым до извлечения данных.
          </div>
        </div>
      </PanelCard>

      {/* Queue Section */}
      {queued.length > 0 && (
        <PanelCard
          title={`Очередь загрузки (${queued.length})`}
          actions={
            <div className="flex gap-2">
              <button
                onClick={clearQueue}
                className="px-3 h-8 rounded bg-line hover:bg-line/60 text-[11px] text-white"
              >
                Очистить
              </button>
              <button
                onClick={uploadQueued}
                disabled={uploading || queued.filter((p) => p.status === "ready").length === 0}
                className="px-3 h-8 rounded bg-accent/80 hover:bg-accent disabled:opacity-40 text-[11px] text-white"
              >
                {uploading ? "Загрузка..." : `Загрузить (${queued.filter((p) => p.status === "ready").length})`}
              </button>
            </div>
          }
        >
          <div className="grid grid-cols-10 gap-2 max-h-96 overflow-auto p-2">
            {queued.map((p) => (
              <div
                key={p.id}
                className="relative group bg-bg-deep rounded-lg border border-line/60 overflow-hidden"
              >
                {/* 50x50 thumbnail */}
                <div className="w-full aspect-square relative">
                  <img
                    src={p.preview}
                    alt={p.file.name}
                    className="w-full h-full object-cover"
                  />

                  {/* Status overlay */}
                  {p.status === "detecting" && (
                    <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                      <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}

                  {p.status === "ready" && (
                    <div className="absolute inset-0 bg-green-500/20 flex items-center justify-center">
                      <div className="text-[8px] text-green-400 font-bold">Готово</div>
                    </div>
                  )}

                  {p.status === "uploading" && (
                    <div className="absolute inset-0 bg-blue-500/20 flex items-center justify-center">
                      <div className="w-4 h-4 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
                    </div>
                  )}

                  {p.status === "done" && (
                    <div className="absolute inset-0 bg-ok/20 flex items-center justify-center">
                      <div className="text-[8px] text-ok font-bold">✓</div>
                    </div>
                  )}

                  {p.status === "failed" && (
                    <div className="absolute inset-0 bg-danger/20 flex items-center justify-center">
                      <div className="text-[8px] text-danger font-bold">✗</div>
                    </div>
                  )}

                  {/* Dataset badge */}
                  {p.dataset === "calibration" && (
                    <div className="absolute top-0.5 right-0.5 px-1 py-0.5 rounded bg-purple-500/80 text-[6px] text-white font-bold">
                      К
                    </div>
                  )}

                  {/* Remove button */}
                  <button
                    onClick={() => removePhoto(p.id)}
                    className="absolute top-0.5 left-0.5 w-4 h-4 rounded bg-danger/80 hover:bg-danger text-[8px] text-white opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    ×
                  </button>
                </div>

                {/* Info */}
                <div className="p-1">
                  <div className="text-[7px] text-muted truncate" title={p.file.name}>
                    {p.file.name}
                  </div>
                  {p.date && (
                    <div className="text-[7px] text-info">{p.date}</div>
                  )}
                  {p.pose && (
                    <div className="text-[7px] text-accent">{p.pose}</div>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Legend */}
          <div className="flex gap-4 mt-2 text-[9px] text-muted px-2">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-black/50 border border-line inline-block" /> Ожидание
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-accent/20 border border-accent/30 inline-block" /> Определение
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-green-500/20 border border-green-500/30 inline-block" /> Готово
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-blue-500/20 border border-blue-500/30 inline-block" /> Загрузка
            </span>
          </div>
        </PanelCard>
      )}
    </Page>
  );
}
