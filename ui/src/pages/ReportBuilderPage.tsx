import { useEffect, useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type Investigation, type AnomalyRecord, type EvidenceBreakdown } from "../api";

import { useApp } from "../store/appStore";
import { EvidenceNote } from "../components/common/EvidenceStatus";
import { evidenceOf } from "../data/evidencePolicy";

interface SavedReport {
  id: string;
  title: string;
  subject: string;
  verdict: "H0" | "H1" | "H2";
  createdAt: string;
  photos: number;
  format: "pdf" | "json" | "html";
}

const SAVED_REPORTS: SavedReport[] = [
  { id: "r-001", title: "Полное расследование 1999–2025", subject: "Субъект 1", verdict: "H1", createdAt: "2025-04-21", photos: 1742, format: "pdf" },
  { id: "r-002", title: "Аудит кластера B (2015–2020)", subject: "Субъект 1", verdict: "H1", createdAt: "2025-04-22", photos: 432, format: "html" },
  { id: "r-003", title: "Проверка покрытия калибровки", subject: "калибровка", verdict: "H0", createdAt: "2025-04-23", photos: 1742, format: "json" },
  { id: "r-004", title: "Кейс подмены 2012", subject: "Субъект 1", verdict: "H1", createdAt: "2025-04-24", photos: 58, format: "pdf" },
];

interface ReportDraft {
  title: string;
  subject: string;
  caseId: string;
  format: "pdf" | "html" | "json";
  range: { from: number; to: number };
  sections: {
    summary: boolean;
    timeline: boolean;
    pairEvidence: boolean;
    anomalies: boolean;
    calibration: boolean;
    photos: boolean;
  };
  notes: string;
}

export default function ReportBuilderPage() {
  const { pairA, pairB } = useApp();
  const [cases, setCases] = useState<Investigation[]>([]);
  const [anomalies, setAnomalies] = useState<AnomalyRecord[]>([]);
  const [evidence, setEvidence] = useState<EvidenceBreakdown | null>(null);
  const [showSaved, setShowSaved] = useState(false);

  const [draft, setDraft] = useState<ReportDraft>({
    title: "FORENSIC_SNAPSHOT_INTERIM",
    subject: "Субъект 1",
    caseId: "inv-001",
    format: "json",
    range: { from: 1999, to: 2025 },
    sections: {
      summary: true,
      timeline: true,
      pairEvidence: true,
      anomalies: true,
      calibration: true,
      photos: false,
    },
    notes: "Автоматическая forensic-компиляция. Только маркеры высокой уверенности.",
  });

  useEffect(() => {
    api.listInvestigations().then(setCases);
    api.listAnomalies().then(setAnomalies);
  }, []);

  useEffect(() => {
    api.getEvidence(pairA, pairB).then(setEvidence);
  }, [pairA, pairB]);

  const includedAnomalies = useMemo(
    () => anomalies.filter((a) => a.year >= draft.range.from && a.year <= draft.range.to),
    [anomalies, draft.range]
  );

  const payload = {
    meta: {
      title: draft.title,
      subject: draft.subject,
      caseId: draft.caseId,
      caseName: cases.find((c) => c.id === draft.caseId)?.name,
      generatedAt: new Date().toISOString(),
      format: draft.format,
      range: draft.range,
    },
    sections: Object.keys(draft.sections).filter(k => (draft.sections as any)[k]),
    payload: {
        summary: draft.sections.summary ? "..." : null,
        anomalies: draft.sections.anomalies ? includedAnomalies.length : 0,
        evidence: draft.sections.pairEvidence ? evidence?.verdict : null
    },
    notes: draft.notes,
  };

  const json = JSON.stringify(payload, null, 2);

  return (
    <Page
      title="Конструктор отчётов"
      subtitle="Настройка forensic-экспорта"
      actions={
        <button
          id="btn_download_json"
          onClick={() => {
            const blob = new Blob([json], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${draft.title}.json`;
            a.click();
            URL.revokeObjectURL(url);
          }}
          className="px-6 h-10 rounded-full bg-accent text-[12px] font-black tracking-widest text-white shadow-lg shadow-accent/20 hover:scale-105 active:scale-95 transition-all"
        >
          СГЕНЕРИРОВАТЬ БАНДЛ
        </button>
      }
    >
      <EvidenceNote level={evidenceOf("report_builder")!.level} className="mb-3">
        <div><strong>Реальная часть:</strong> {evidenceOf("report_builder")!.realPart || "нет"}</div>
        <div><strong>Заглушка:</strong> {evidenceOf("report_builder")!.stubPart}</div>
        <div><strong>Для перехода:</strong> {evidenceOf("report_builder")!.upgradeHint}</div>
      </EvidenceNote>
      {/* Saved reports (merged from ReportsPage) */}
      <PanelCard
        title={`📁 Сохранённые отчёты (${SAVED_REPORTS.length})`}
        className="mb-4"
      >
        <button
          onClick={() => setShowSaved(!showSaved)}
          className="text-[10px] text-muted hover:text-white mb-2 transition-colors"
        >
          {showSaved ? "▾ Скрыть список" : "▸ Показать список"}
        </button>
        {showSaved && (
          <table className="w-full text-[11px]">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-2">id</th>
                <th className="text-left p-2">название</th>
                <th className="text-left p-2">субъект</th>
                <th className="text-left p-2">вердикт</th>
                <th className="text-left p-2">фото</th>
                <th className="text-left p-2">создан</th>
                <th className="text-left p-2">формат</th>
                <th className="text-right p-2"></th>
              </tr>
            </thead>
            <tbody>
              {SAVED_REPORTS.map((r) => (
                <tr key={r.id} className="border-b border-line/40">
                  <td className="p-2 font-mono text-white">{r.id}</td>
                  <td className="p-2 text-white">{r.title}</td>
                  <td className="p-2 text-muted">{r.subject}</td>
                  <td className="p-2">
                    <span
                      className={`px-1.5 py-0.5 rounded text-[10px] ${
                        r.verdict === "H0" ? "bg-ok/30 text-ok" : r.verdict === "H1" ? "bg-danger/30 text-danger" : "bg-warn/30 text-warn"
                      }`}
                    >
                      {r.verdict}
                    </span>
                  </td>
                  <td className="p-2 font-mono text-white">{r.photos}</td>
                  <td className="p-2 text-muted">{r.createdAt}</td>
                  <td className="p-2 uppercase text-white">{r.format}</td>
                  <td className="p-2 text-right">
                    <button className="px-2 h-6 rounded bg-line/60 hover:bg-line text-[10px] text-white mr-1">
                      Открыть
                    </button>
                    <button className="px-2 h-6 rounded bg-info/60 hover:bg-info text-[10px] text-white">
                      Экспорт
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </PanelCard>

      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left: Controls */}
        <div className="md:col-span-5 space-y-4">
          <PanelCard title="🏷️ Метаданные" className="bg-bg-deep/50">
            <div className="space-y-4">
              <Field label="Название документа">
                <input
                  id="inp_title"
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px] outline-none focus:border-accent transition-colors"
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Целевой субъект">
                  <input
                    id="inp_subject"
                    value={draft.subject}
                    onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
                    className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px]"
                  />
                </Field>
                <Field label="Активное расследование">
                  <select
                    id="sel_case"
                    value={draft.caseId}
                    onChange={(e) => setDraft({ ...draft, caseId: e.target.value })}
                    className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px] outline-none"
                  >
                    {cases.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                  </select>
                </Field>
              </div>
            </div>
          </PanelCard>

          <PanelCard title="📅 Объём и формат">
            <div className="grid grid-cols-3 gap-3">
              <Field label="С">
                <input
                  id="inp_range_from"
                  type="number"
                  value={draft.range.from}
                  onChange={(e) => setDraft({ ...draft, range: { ...draft.range, from: +e.target.value } })}
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px]"
                />
              </Field>
              <Field label="По">
                <input
                  id="inp_range_to"
                  type="number"
                  value={draft.range.to}
                  onChange={(e) => setDraft({ ...draft, range: { ...draft.range, to: +e.target.value } })}
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px]"
                />
              </Field>
              <Field label="Тип MIME">
                <select
                  id="sel_format"
                  value={draft.format}
                  onChange={(e) => setDraft({ ...draft, format: e.target.value as any })}
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px]"
                >
                  <option value="json">JSON</option>
                  <option value="html">HTML</option>
                  <option value="pdf">PDF</option>
                </select>
              </Field>
            </div>
          </PanelCard>

          <PanelCard title="🧩 Выбор компонентов">
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 py-2">
              {(Object.keys(draft.sections) as Array<keyof typeof draft.sections>).map((k) => (
                <label key={k} className="flex items-center justify-between cursor-pointer group p-2 rounded-xl hover:bg-white/5 transition-colors">
                  <span className="text-[11px] font-bold text-muted group-hover:text-white uppercase tracking-tighter">{k}</span>
                  <input
                    id={`chk_section_${k}`}
                    type="checkbox"
                    checked={draft.sections[k]}
                    onChange={(e) =>
                      setDraft({ ...draft, sections: { ...draft.sections, [k]: e.target.checked } })
                    }
                    className="w-4 h-4 rounded-full border-line accent-accent transition-all"
                  />
                </label>
              ))}
            </div>
          </PanelCard>

          <PanelCard title="📝 Пояснительные заметки">
            <textarea
              id="txt_notes"
              rows={4}
              className="w-full px-3 py-2 bg-bg-deep border border-line rounded-2xl text-white text-[11px] outline-none focus:border-accent transition-all resize-none"
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              placeholder="Введите контекст анализа..."
            />
          </PanelCard>
        </div>

        {/* Right: Preview */}
        <div className="md:col-span-7">
          <PanelCard title="📦 Предпросмотр бандла" className="h-full flex flex-col bg-black/20 border-line/20">
            <div className="flex items-center justify-between mb-4 px-1">
              <div className="flex gap-4">
                <div className="text-[10px] text-muted font-bold uppercase tracking-widest flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-info"></span>
                  {Object.values(draft.sections).filter(Boolean).length} блоков
                </div>
                <div className="text-[10px] text-muted font-bold uppercase tracking-widest flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-warn"></span>
                  {includedAnomalies.length} помечено
                </div>
              </div>
              <div className="text-[10px] font-mono text-accent">{draft.format.toUpperCase()} VERSION 1.0</div>
            </div>
            
            <div className="flex-1 bg-black/60 rounded-3xl border border-line p-6 shadow-inner overflow-hidden flex flex-col">
              <pre className="flex-1 text-[11px] text-info/70 font-mono whitespace-pre-wrap overflow-auto custom-scrollbar no-scrollbar">
                {json}
              </pre>
            </div>
          </PanelCard>
        </div>
      </div>
    </Page>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5 text-[11px]">
      <span className="text-muted font-black uppercase tracking-widest pl-1 text-[9px]">{label}</span>
      {children}
    </label>
  );
}
