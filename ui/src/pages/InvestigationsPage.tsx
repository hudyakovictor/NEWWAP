import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type Investigation } from "../api";

const EMPTY: Investigation = {
  id: "",
  name: "",
  subject: "Субъект 1",
  createdAt: "",
  updatedAt: "",
  photoCount: 0,
  verdict: "open",
  notes: "",
  tags: [],
};

export default function InvestigationsPage() {
  const [items, setItems] = useState<Investigation[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Investigation | null>(null);

  useEffect(() => {
    api.listInvestigations().then((r) => {
      setItems(r);
      setLoading(false);
      if (r.length && !selectedId) setSelectedId(r[0].id);
    });
  }, []);

  const selected = items.find((x) => x.id === selectedId) ?? null;

  function startNew() {
    const now = new Date().toISOString().slice(0, 10);
    setDraft({
      ...EMPTY,
      id: `inv-${Date.now().toString(36)}`,
      createdAt: now,
      updatedAt: now,
    });
  }

  async function save() {
    if (!draft) return;
    const updated = { ...draft, updatedAt: new Date().toISOString().slice(0, 10) };
    const saved = await api.upsertInvestigation(updated);
    setItems((prev) => {
      const idx = prev.findIndex((x) => x.id === saved.id);
      if (idx >= 0) {
        const next = prev.slice();
        next[idx] = saved;
        return next;
      }
      return [saved, ...prev];
    });
    setSelectedId(saved.id);
    setDraft(null);
  }

  async function remove(id: string) {
    await api.deleteInvestigation(id);
    setItems((prev) => prev.filter((x) => x.id !== id));
    if (selectedId === id) setSelectedId(null);
  }

  return (
    <Page
      title="Кейсы"
      subtitle="Форензические расследования · субъекты, заметки, вердикты"
      actions={
        <button onClick={startNew} className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">
          + Новый кейс
        </button>
      }
    >
      {loading ? (
        <div className="text-[11px] text-muted">Загрузка…</div>
      ) : (
        <div className="grid grid-cols-12 gap-3">
          <div className="col-span-4">
            <PanelCard title={`Все кейсы (${items.length})`}>
              <div className="flex flex-col gap-1">
                {items.map((i) => (
                  <button
                    key={i.id}
                    onClick={() => {
                      setSelectedId(i.id);
                      setDraft(null);
                    }}
                    className={`text-left px-2 py-2 rounded border ${
                      selectedId === i.id
                        ? "bg-line/70 border-info"
                        : "bg-bg-deep border-line/60 hover:border-axis"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] text-white font-semibold">{i.name}</span>
                      <span
                        className={`text-[9px] px-1 rounded ${
                          i.verdict === "H0"
                            ? "bg-ok/30 text-ok"
                            : i.verdict === "H1"
                            ? "bg-danger/30 text-danger"
                            : i.verdict === "H2"
                            ? "bg-warn/30 text-warn"
                            : "bg-muted/30 text-muted"
                        }`}
                      >
                        {i.verdict}
                      </span>
                    </div>
                    <div className="text-[10px] text-muted">
                      {i.subject} · {i.photoCount} фото · обн. {i.updatedAt}
                    </div>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {i.tags.map((t) => (
                        <span key={t} className="text-[8px] px-1 rounded bg-line text-muted">
                          {t}
                        </span>
                      ))}
                    </div>
                  </button>
                ))}
              </div>
            </PanelCard>
          </div>

          <div className="col-span-8">
            {draft ? (
              <EditForm
                value={draft}
                onChange={setDraft}
                onSave={save}
                onCancel={() => setDraft(null)}
              />
            ) : selected ? (
              <PanelCard
                title={selected.name}
                actions={
                  <div className="flex gap-1">
                    <button
                      onClick={() => setDraft(selected)}
                      className="px-2 h-6 rounded bg-info/60 hover:bg-info text-[10px] text-white"
                    >
                      Ред.
                    </button>
                    <button
                      onClick={() => remove(selected.id)}
                      className="px-2 h-6 rounded bg-danger/60 hover:bg-danger text-[10px] text-white"
                    >
                      Удалить
                    </button>
                  </div>
                }
              >
                <div className="grid grid-cols-4 gap-2 text-[11px] mb-3">
                  <KV k="id" v={selected.id} />
                  <KV k="субъект" v={selected.subject} />
                  <KV k="создано" v={selected.createdAt} />
                  <KV k="обновлено" v={selected.updatedAt} />
                  <KV k="фото" v={selected.photoCount} />
                  <KV k="вердикт" v={selected.verdict} />
                  <KV k="теги" v={selected.tags.join(", ") || "—"} />
                </div>
                <div className="text-[11px] text-muted uppercase tracking-widest mb-1">Заметки</div>
                <div className="text-[11px] text-white whitespace-pre-wrap bg-bg-deep/50 border border-line/60 rounded p-2">
                  {selected.notes || "Нет заметок."}
                </div>
              </PanelCard>
            ) : (
              <div className="text-[11px] text-muted">Выберите кейс слева.</div>
            )}
          </div>
        </div>
      )}
    </Page>
  );
}

function EditForm({
  value,
  onChange,
  onSave,
  onCancel,
}: {
  value: Investigation;
  onChange: (v: Investigation) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <PanelCard
      title={value.id.startsWith("inv-") && !value.name ? "Новый кейс" : `Ред. — ${value.name || value.id}`}
    >
      <div className="grid grid-cols-2 gap-3 text-[11px]">
        <Field label="Название">
          <input
            className="w-full h-8 px-2 bg-bg-deep border border-line rounded text-white"
            value={value.name}
            onChange={(e) => onChange({ ...value, name: e.target.value })}
          />
        </Field>
        <Field label="Субъект">
          <input
            className="w-full h-8 px-2 bg-bg-deep border border-line rounded text-white"
            value={value.subject}
            onChange={(e) => onChange({ ...value, subject: e.target.value })}
          />
        </Field>
        <Field label="Кол-во фото">
          <input
            type="number"
            className="w-full h-8 px-2 bg-bg-deep border border-line rounded text-white"
            value={value.photoCount}
            onChange={(e) => onChange({ ...value, photoCount: +e.target.value })}
          />
        </Field>
        <Field label="Вердикт">
          <select
            className="w-full h-8 px-2 bg-bg-deep border border-line rounded text-white"
            value={value.verdict}
            onChange={(e) => onChange({ ...value, verdict: e.target.value as any })}
          >
            {(["open", "H0", "H1", "H2"] as const).map((v) => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
        </Field>
        <Field label="Теги (через запятую)" full>
          <input
            className="w-full h-8 px-2 bg-bg-deep border border-line rounded text-white"
            value={value.tags.join(", ")}
            onChange={(e) =>
              onChange({
                ...value,
                tags: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
              })
            }
          />
        </Field>
        <Field label="Заметки" full>
          <textarea
            rows={6}
            className="w-full px-2 py-1 bg-bg-deep border border-line rounded text-white"
            value={value.notes}
            onChange={(e) => onChange({ ...value, notes: e.target.value })}
          />
        </Field>
      </div>
      <div className="flex gap-2 mt-3">
        <button onClick={onSave} className="px-3 h-8 rounded bg-ok/70 hover:bg-ok text-[11px] text-white">
          Сохранить
        </button>
        <button onClick={onCancel} className="px-3 h-8 rounded bg-line text-[11px] text-white">
          Отмена
        </button>
      </div>
    </PanelCard>
  );
}

function Field({ label, children, full = false }: { label: string; children: React.ReactNode; full?: boolean }) {
  return (
    <label className={`flex flex-col gap-1 ${full ? "col-span-2" : ""}`}>
      <span className="text-muted">{label}</span>
      {children}
    </label>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-line/40 py-0.5">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-white truncate max-w-[60%] text-right">{v}</span>
    </div>
  );
}
