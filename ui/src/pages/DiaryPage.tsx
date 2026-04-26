import { useState, useEffect } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api } from "../api";
import type { DiaryEntry, HypothesisStatus } from "../api/types";

const STATUS_LABELS: Record<HypothesisStatus, string> = {
  open: "Открыта",
  confirmed: "Подтверждена",
  rejected: "Опровергнута",
  needs_data: "Нужны данные",
};

const STATUS_COLORS: Record<HypothesisStatus, string> = {
  open: "bg-yellow-100 text-yellow-800",
  confirmed: "bg-green-100 text-green-800",
  rejected: "bg-red-100 text-red-800",
  needs_data: "bg-blue-100 text-blue-800",
};

export default function DiaryPage() {
  const [entries, setEntries] = useState<DiaryEntry[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [newEntry, setNewEntry] = useState("");
  const [newHypothesis, setNewHypothesis] = useState("");
  const [selectedEntry, setSelectedEntry] = useState<string | null>(null);

  useEffect(() => {
    loadDiary();
  }, []);

  async function loadDiary() {
    try {
      const data = await api.getDiaryEntries();
      setEntries(data.entries);
    } catch (e) {
      console.error("Ошибка загрузки дневника", e);
    } finally {
      setIsLoading(false);
    }
  }

  async function addEntry() {
    if (!newEntry.trim()) return;

    try {
      const entry = await api.addDiaryEntry({
        content: newEntry,
        type: "observation",
        timestamp: new Date().toISOString(),
      });
      setEntries([entry, ...entries]);
      setNewEntry("");
    } catch (e) {
      console.error("Ошибка добавления записи", e);
    }
  }

  async function addHypothesis() {
    if (!newHypothesis.trim()) return;

    try {
      const entry = await api.addDiaryEntry({
        content: newHypothesis,
        type: "hypothesis",
        status: "open",
        timestamp: new Date().toISOString(),
      });
      setEntries([entry, ...entries]);
      setNewHypothesis("");
    } catch (e) {
      console.error("Ошибка добавления гипотезы", e);
    }
  }

  async function updateStatus(id: string, status: HypothesisStatus) {
    try {
      await api.updateDiaryEntry(id, { status });
      setEntries(entries.map(e => e.id === id ? { ...e, status } : e));
    } catch (e) {
      console.error("Ошибка обновления статуса", e);
    }
  }

  const hypotheses = entries.filter(e => e.type === "hypothesis");
  const observations = entries.filter(e => e.type === "observation");
  const conclusions = entries.filter(e => e.type === "conclusion");

  return (
    <Page title="Дневник исследователя">
      {isLoading && <div className="text-sm text-muted mb-2">Загрузка...</div>}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Новая запись */}
        <PanelCard title="Новое наблюдение" className="lg:col-span-2">
          <textarea
            value={newEntry}
            onChange={(e) => setNewEntry(e.target.value)}
            placeholder="Опишите наблюдение, факт или находку..."
            className="w-full h-24 p-2 border rounded text-sm font-mono"
          />
          <div className="flex gap-2 mt-2">
            <button
              onClick={addEntry}
              disabled={!newEntry.trim()}
              className="px-3 py-1 bg-primary text-white rounded text-sm disabled:opacity-50"
            >
              Записать наблюдение
            </button>
          </div>
        </PanelCard>

        <PanelCard title="Новая гипотеза">
          <textarea
            value={newHypothesis}
            onChange={(e) => setNewHypothesis(e.target.value)}
            placeholder="Выдвинуть гипотезу..."
            className="w-full h-24 p-2 border rounded text-sm font-mono"
          />
          <div className="flex gap-2 mt-2">
            <button
              onClick={addHypothesis}
              disabled={!newHypothesis.trim()}
              className="px-3 py-1 bg-primary text-white rounded text-sm disabled:opacity-50"
            >
              Выдвинуть гипотезу
            </button>
          </div>
        </PanelCard>

        {/* Гипотезы */}
        <PanelCard title={`Гипотезы (${hypotheses.length})`} className="lg:col-span-1">
          {hypotheses.length === 0 ? (
            <div className="text-muted text-sm">Нет активных гипотез</div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {hypotheses.map((h) => (
                <div
                  key={h.id}
                  className={`p-2 rounded border cursor-pointer ${
                    selectedEntry === h.id ? "border-primary bg-primary/5" : "border-border"
                  }`}
                  onClick={() => setSelectedEntry(h.id === selectedEntry ? null : h.id)}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs px-2 py-0.5 rounded ${STATUS_COLORS[h.status || "open"]}`}>
                      {STATUS_LABELS[h.status || "open"]}
                    </span>
                    <span className="text-xs text-muted">
                      {new Date(h.timestamp).toLocaleDateString("ru-RU")}
                    </span>
                  </div>
                  <div className="text-sm">{h.content}</div>
                  
                  {selectedEntry === h.id && (
                    <div className="flex gap-1 mt-2 pt-2 border-t">
                      <button
                        onClick={(e) => { e.stopPropagation(); updateStatus(h.id, "confirmed"); }}
                        className="text-xs px-2 py-1 bg-green-100 rounded hover:bg-green-200"
                      >
                        Подтвердить
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); updateStatus(h.id, "rejected"); }}
                        className="text-xs px-2 py-1 bg-red-100 rounded hover:bg-red-200"
                      >
                        Опровергнуть
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); updateStatus(h.id, "needs_data"); }}
                        className="text-xs px-2 py-1 bg-blue-100 rounded hover:bg-blue-200"
                      >
                        Нужны данные
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </PanelCard>

        {/* Наблюдения */}
        <PanelCard title={`Наблюдения (${observations.length})`} className="lg:col-span-1">
          {observations.length === 0 ? (
            <div className="text-muted text-sm">Нет записанных наблюдений</div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {observations.map((o) => (
                <div key={o.id} className="p-2 rounded border border-border">
                  <div className="text-xs text-muted mb-1">
                    {new Date(o.timestamp).toLocaleString("ru-RU")}
                  </div>
                  <div className="text-sm font-mono">{o.content}</div>
                </div>
              ))}
            </div>
          )}
        </PanelCard>

        {/* Выводы */}
        <PanelCard title={`Выводы (${conclusions.length})`} className="lg:col-span-1">
          {conclusions.length === 0 ? (
            <div className="text-muted text-sm">Нет сформированных выводов</div>
          ) : (
            <div className="space-y-2 max-h-96 overflow-y-auto">
              {conclusions.map((c) => (
                <div key={c.id} className="p-2 rounded border border-border bg-primary/5">
                  <div className="text-xs text-muted mb-1">
                    {new Date(c.timestamp).toLocaleDateString("ru-RU")}
                  </div>
                  <div className="text-sm font-medium">{c.content}</div>
                </div>
              ))}
            </div>
          )}
        </PanelCard>
      </div>

      <PanelCard title="Статистика расследования" className="mt-4">
        <div className="grid grid-cols-4 gap-4 text-center">
          <div>
            <div className="text-2xl font-bold">{hypotheses.filter(h => h.status === "open").length}</div>
            <div className="text-xs text-muted">Открытые гипотезы</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{hypotheses.filter(h => h.status === "confirmed").length}</div>
            <div className="text-xs text-muted">Подтверждено</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{hypotheses.filter(h => h.status === "rejected").length}</div>
            <div className="text-xs text-muted">Опровергнуто</div>
          </div>
          <div>
            <div className="text-2xl font-bold">{observations.length}</div>
            <div className="text-xs text-muted">Наблюдений</div>
          </div>
        </div>
      </PanelCard>
    </Page>
  );
}
