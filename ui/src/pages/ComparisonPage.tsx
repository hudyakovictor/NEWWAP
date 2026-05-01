import { useState, useRef } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { ALL_PHOTOS } from "../data/photoRegistry";
import { api, type EvidenceBreakdown } from "../api";

export default function ComparisonPage() {
  const [photoA, setPhotoA] = useState<string>("");
  const [photoB, setPhotoB] = useState<string>("");
  const [uploadedA, setUploadedA] = useState<File | null>(null);
  const [uploadedB, setUploadedB] = useState<File | null>(null);
  const [evidence, setEvidence] = useState<EvidenceBreakdown | null>(null);
  const [loading, setLoading] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  // Settings refs
  const threshold1Ref = useRef<HTMLInputElement>(null);
  const threshold2Ref = useRef<HTMLInputElement>(null);
  const threshold3Ref = useRef<HTMLInputElement>(null);
  const threshold4Ref = useRef<HTMLInputElement>(null);

  // Load photos from database
  const mainPhotos = ALL_PHOTOS.filter(p => p.folder === "main");
  const calibrationPhotos = ALL_PHOTOS.filter(p => p.folder === "myface");

  const handleCompare = async () => {
    setLoading(true);
    try {
      let idA = photoA;
      let idB = photoB;

      // If uploaded files, extract them first
      if (uploadedA) {
        const formData = new FormData();
        formData.append("file", uploadedA);
        const result = await fetch("/api/extract/upload", {
          method: "POST",
          body: formData,
        }).then(r => r.json());
        idA = result.photo_id;
      }

      if (uploadedB) {
        const formData = new FormData();
        formData.append("file", uploadedB);
        const result = await fetch("/api/extract/upload", {
          method: "POST",
          body: formData,
        }).then(r => r.json());
        idB = result.photo_id;
      }

      if (idA && idB) {
        const ev = await api.getEvidence(idA, idB);
        setEvidence(ev);
      }
    } catch (e) {
      console.error("Comparison failed:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleReset = async () => {
    if (confirm("Вы уверены? Это удалит все извлеченные данные (но не исходные фото).")) {
      await fetch("/api/reset-all", { method: "POST" });
      window.location.reload();
    }
  };

  return (
    <Page title="Сравнение фотографий">
      <div className="space-y-4">
        {/* Photo Selection */}
        <div className="grid grid-cols-2 gap-4">
          <PanelCard title="Фото A">
            <div className="space-y-3">
              <div>
                <label className="block text-[10px] text-muted mb-1">Выбрать из базы:</label>
                <select
                  value={photoA}
                  onChange={(e) => { setPhotoA(e.target.value); setUploadedA(null); }}
                  className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                >
                  <option value="">-- Выберите фото --</option>
                  <optgroup label="Основная база">
                    {mainPhotos.map(p => (
                      <option key={p.id} value={p.id}>{p.id} ({p.pose?.classification})</option>
                    ))}
                  </optgroup>
                  <optgroup label="Калибровка">
                    {calibrationPhotos.map(p => (
                      <option key={p.id} value={p.id}>{p.id} ({p.pose?.classification})</option>
                    ))}
                  </optgroup>
                </select>
              </div>
              <div className="text-[10px] text-muted">или</div>
              <div>
                <label className="block text-[10px] text-muted mb-1">Загрузить новое:</label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => { setUploadedA(e.target.files?.[0] || null); setPhotoA(""); }}
                  className="w-full text-[10px]"
                />
              </div>
              {uploadedA && (
                <div className="text-[10px] text-ok">Выбрано: {uploadedA.name}</div>
              )}
            </div>
          </PanelCard>

          <PanelCard title="Фото B">
            <div className="space-y-3">
              <div>
                <label className="block text-[10px] text-muted mb-1">Выбрать из базы:</label>
                <select
                  value={photoB}
                  onChange={(e) => { setPhotoB(e.target.value); setUploadedB(null); }}
                  className="w-full bg-bg border border-line rounded px-2 py-1.5 text-[11px]"
                >
                  <option value="">-- Выберите фото --</option>
                  <optgroup label="Основная база">
                    {mainPhotos.map(p => (
                      <option key={p.id} value={p.id}>{p.id} ({p.pose?.classification})</option>
                    ))}
                  </optgroup>
                  <optgroup label="Калибровка">
                    {calibrationPhotos.map(p => (
                      <option key={p.id} value={p.id}>{p.id} ({p.pose?.classification})</option>
                    ))}
                  </optgroup>
                </select>
              </div>
              <div className="text-[10px] text-muted">или</div>
              <div>
                <label className="block text-[10px] text-muted mb-1">Загрузить новое:</label>
                <input
                  type="file"
                  accept="image/*"
                  onChange={(e) => { setUploadedB(e.target.files?.[0] || null); setPhotoB(""); }}
                  className="w-full text-[10px]"
                />
              </div>
              {uploadedB && (
                <div className="text-[10px] text-ok">Выбрано: {uploadedB.name}</div>
              )}
            </div>
          </PanelCard>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          <button
            onClick={handleCompare}
            disabled={loading || (!photoA && !uploadedA) || (!photoB && !uploadedB)}
            className="px-4 py-2 rounded bg-ok hover:bg-ok/80 text-white text-[11px] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Сравнение..." : "Сравнить"}
          </button>
          <button
            onClick={() => setShowSettings(true)}
            className="px-4 py-2 rounded bg-line hover:bg-line/80 text-white text-[11px]"
          >
            Настройки тепловой карты
          </button>
          <button
            onClick={handleReset}
            className="px-4 py-2 rounded bg-danger hover:bg-danger/80 text-white text-[11px]"
          >
            Сбросить все данные
          </button>
        </div>

        {/* Results */}
        {evidence && (
          <div className="space-y-4">
            <PanelCard title="Результаты сравнения">
              <div className="space-y-3">
                <div className="text-[11px]">
                  <strong>Вердикт:</strong> {evidence.verdict}
                </div>
                <div className="text-[11px]">
                  <strong>H0 (тот же человек):</strong> {(evidence.posteriors.H0 * 100).toFixed(1)}%
                </div>
                <div className="text-[11px]">
                  <strong>H1 (синтетика/маска):</strong> {(evidence.posteriors.H1 * 100).toFixed(1)}%
                </div>
                <div className="text-[11px]">
                  <strong>H2 (разные люди):</strong> {(evidence.posteriors.H2 * 100).toFixed(1)}%
                </div>
              </div>
            </PanelCard>

            <PanelCard title="Метрики геометрии">
              <div className="text-[11px] text-muted">
                Детальное сравнение костных метрик будет добавлено...
              </div>
            </PanelCard>

            <PanelCard title="Метрики текстуры">
              <div className="text-[11px] text-muted">
                Детальное сравнение текстурных метрик будет добавлено...
              </div>
            </PanelCard>

            <PanelCard title="Тепловая карта различий">
              <div className="text-[11px] text-muted">
                Визуализация тепловой карты будет добавлена...
              </div>
            </PanelCard>
          </div>
        )}

        {/* Settings Popup */}
        {showSettings && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
            <div className="bg-bg rounded-lg p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-bold">Настройки тепловой карты</h2>
                <button
                  onClick={() => setShowSettings(false)}
                  className="text-muted hover:text-white"
                >
                  ✕
                </button>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] text-muted mb-2">
                    Порог 1: Сине-голубой переход (0-{threshold1Ref.current?.value || 25}%)
                  </label>
                  <input
                    ref={threshold1Ref}
                    type="range"
                    min="0"
                    max="50"
                    defaultValue="25"
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-muted mb-2">
                    Порог 2: Голубо-зеленый переход ({threshold1Ref.current?.value || 25}-{threshold2Ref.current?.value || 50}%)
                  </label>
                  <input
                    ref={threshold2Ref}
                    type="range"
                    min="25"
                    max="75"
                    defaultValue="50"
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-muted mb-2">
                    Порог 3: Зелено-желтый переход ({threshold2Ref.current?.value || 50}-{threshold3Ref.current?.value || 75}%)
                  </label>
                  <input
                    ref={threshold3Ref}
                    type="range"
                    min="50"
                    max="90"
                    defaultValue="75"
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-[10px] text-muted mb-2">
                    Порог 4: Желто-красный переход ({threshold3Ref.current?.value || 75}-{threshold4Ref.current?.value || 100}%)
                  </label>
                  <input
                    ref={threshold4Ref}
                    type="range"
                    min="75"
                    max="100"
                    defaultValue="90"
                    className="w-full"
                  />
                </div>
                <button
                  onClick={() => setShowSettings(false)}
                  className="w-full px-4 py-2 rounded bg-ok hover:bg-ok/80 text-white text-[11px]"
                >
                  Применить
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Page>
  );
}
