import { useEffect, useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type Investigation, type AnomalyRecord, type EvidenceBreakdown } from "../api";

import { useApp } from "../store/appStore";

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

  const [draft, setDraft] = useState<ReportDraft>({
    title: "FORENSIC_SNAPSHOT_INTERIM",
    subject: "Subject 1",
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
    notes: "Automated forensic compilation. High confidence markers only.",
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
      title="Report Architect"
      subtitle="Configure forensic export bundle"
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
          GENERATE BUNDLE
        </button>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
        {/* Left: Controls */}
        <div className="md:col-span-5 space-y-4">
          <PanelCard title="🏷️ Metadata" className="bg-bg-deep/50">
            <div className="space-y-4">
              <Field label="Document Title">
                <input
                  id="inp_title"
                  value={draft.title}
                  onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px] outline-none focus:border-accent transition-colors"
                />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Target Subject">
                  <input
                    id="inp_subject"
                    value={draft.subject}
                    onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
                    className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px]"
                  />
                </Field>
                <Field label="Active Investigation">
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

          <PanelCard title="📅 Scope & Format">
            <div className="grid grid-cols-3 gap-3">
              <Field label="Range From">
                <input
                  id="inp_range_from"
                  type="number"
                  value={draft.range.from}
                  onChange={(e) => setDraft({ ...draft, range: { ...draft.range, from: +e.target.value } })}
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px]"
                />
              </Field>
              <Field label="Range To">
                <input
                  id="inp_range_to"
                  type="number"
                  value={draft.range.to}
                  onChange={(e) => setDraft({ ...draft, range: { ...draft.range, to: +e.target.value } })}
                  className="w-full h-9 px-3 rounded-xl bg-bg-deep border border-line text-white text-[11px]"
                />
              </Field>
              <Field label="MIME Type">
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

          <PanelCard title="🧩 Component Selection">
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

          <PanelCard title="📝 Executive Notes">
            <textarea
              id="txt_notes"
              rows={4}
              className="w-full px-3 py-2 bg-bg-deep border border-line rounded-2xl text-white text-[11px] outline-none focus:border-accent transition-all resize-none"
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
              placeholder="Enter analysis context..."
            />
          </PanelCard>
        </div>

        {/* Right: Preview */}
        <div className="md:col-span-7">
          <PanelCard title="📦 Final Payload Preview" className="h-full flex flex-col bg-black/20 border-line/20">
            <div className="flex items-center justify-between mb-4 px-1">
              <div className="flex gap-4">
                <div className="text-[10px] text-muted font-bold uppercase tracking-widest flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-info"></span>
                  {Object.values(draft.sections).filter(Boolean).length} Units
                </div>
                <div className="text-[10px] text-muted font-bold uppercase tracking-widest flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-warn"></span>
                  {includedAnomalies.length} Flagged
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
