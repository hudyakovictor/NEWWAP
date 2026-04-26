import { useEffect, useMemo, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type Investigation, type AnomalyRecord, type EvidenceBreakdown } from "../api";
import { PHOTOS } from "../mock/photos";
import { useApp } from "../store/appStore";
import StubBanner from "../components/common/StubBanner";

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
    title: "DEEPUTIN · interim report",
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
    notes: "Interim automated report — requires expert review before publishing.",
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

  const photoSample = useMemo(
    () => PHOTOS.filter((p) => p.year >= draft.range.from && p.year <= draft.range.to).slice(0, 10),
    [draft.range]
  );

  const selectedCase = cases.find((c) => c.id === draft.caseId);

  const payload = {
    meta: {
      title: draft.title,
      subject: draft.subject,
      caseId: draft.caseId,
      caseName: selectedCase?.name,
      verdict: selectedCase?.verdict,
      generatedAt: new Date().toISOString(),
      format: draft.format,
      range: draft.range,
    },
    ...(draft.sections.summary && {
      summary: {
        totalPhotos: PHOTOS.length,
        inRange: PHOTOS.filter((p) => p.year >= draft.range.from && p.year <= draft.range.to).length,
        headline: "Automated pipeline identifies elevated H1 evidence in 2012 / 2014 / 2023 windows.",
      },
    }),
    ...(draft.sections.pairEvidence && evidence
      ? {
          pairEvidence: {
            aId: evidence.aId,
            bId: evidence.bId,
            verdict: evidence.verdict,
            posteriors: evidence.posteriors,
            chronologyFlags: evidence.chronology.flags,
          },
        }
      : {}),
    ...(draft.sections.anomalies && {
      anomalies: includedAnomalies.map((a) => ({
        id: a.id,
        year: a.year,
        severity: a.severity,
        kind: a.kind,
        title: a.title,
        resolved: a.resolved,
      })),
    }),
    ...(draft.sections.calibration && {
      calibration: {
        note: "see /api/calibration/summary",
        aggregate: "medium",
      },
    }),
    ...(draft.sections.photos && {
      photos: photoSample.map((p) => ({
        id: p.id,
        year: p.year,
        cluster: p.cluster,
        flags: p.flags,
      })),
    }),
    notes: draft.notes,
  };

  const json = JSON.stringify(payload, null, 2);

  return (
    <Page
      title="Report builder (debug)"
      subtitle="Compose a forensic export payload from the current state"
      actions={
        <button
          onClick={() => {
            const blob = new Blob([json], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${draft.title.replace(/\s+/g, "_")}.json`;
            a.click();
            URL.revokeObjectURL(url);
          }}
          className="px-3 h-8 rounded bg-accent/80 hover:bg-accent text-[11px] text-white"
        >
          Download JSON
        </button>
      }
    >
      <StubBanner note="Most report sections still draw from stub fields. Export only what the Progress page marks as real." />

      <div className="grid grid-cols-12 gap-3">
        <div className="col-span-5 flex flex-col gap-3">
          <PanelCard title="Meta">
            <Field label="Title">
              <input
                value={draft.title}
                onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-white text-[11px]"
              />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Subject">
                <input
                  value={draft.subject}
                  onChange={(e) => setDraft({ ...draft, subject: e.target.value })}
                  className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-white text-[11px]"
                />
              </Field>
              <Field label="Case">
                <select
                  value={draft.caseId}
                  onChange={(e) => setDraft({ ...draft, caseId: e.target.value })}
                  className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-white text-[11px]"
                >
                  {cases.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-3 gap-2">
              <Field label="From year">
                <input
                  type="number"
                  value={draft.range.from}
                  onChange={(e) => setDraft({ ...draft, range: { ...draft.range, from: +e.target.value } })}
                  className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-white text-[11px]"
                />
              </Field>
              <Field label="To year">
                <input
                  type="number"
                  value={draft.range.to}
                  onChange={(e) => setDraft({ ...draft, range: { ...draft.range, to: +e.target.value } })}
                  className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-white text-[11px]"
                />
              </Field>
              <Field label="Format">
                <select
                  value={draft.format}
                  onChange={(e) => setDraft({ ...draft, format: e.target.value as any })}
                  className="w-full h-8 px-2 rounded bg-bg-deep border border-line text-white text-[11px]"
                >
                  <option value="json">json</option>
                  <option value="html">html</option>
                  <option value="pdf">pdf</option>
                </select>
              </Field>
            </div>
          </PanelCard>

          <PanelCard title="Sections">
            {(Object.keys(draft.sections) as Array<keyof typeof draft.sections>).map((k) => (
              <label key={k} className="flex items-center gap-2 text-[11px] text-white py-1">
                <input
                  type="checkbox"
                  checked={draft.sections[k]}
                  onChange={(e) =>
                    setDraft({ ...draft, sections: { ...draft.sections, [k]: e.target.checked } })
                  }
                />
                {k}
              </label>
            ))}
          </PanelCard>

          <PanelCard title="Notes">
            <textarea
              rows={6}
              className="w-full px-2 py-1 bg-bg-deep border border-line rounded text-white text-[11px]"
              value={draft.notes}
              onChange={(e) => setDraft({ ...draft, notes: e.target.value })}
            />
          </PanelCard>
        </div>
        <div className="col-span-7">
          <PanelCard title="Preview payload" className="h-full flex flex-col">
            <div className="text-[11px] text-muted mb-2">
              {Object.values(draft.sections).filter(Boolean).length} section(s) · includes {includedAnomalies.length} anomalies
            </div>
            <pre className="flex-1 text-[11px] bg-black/60 border border-line rounded p-2 overflow-auto text-muted font-mono whitespace-pre-wrap">
              {json}
            </pre>
          </PanelCard>
        </div>
      </div>
    </Page>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-[11px] my-1">
      <span className="text-muted">{label}</span>
      {children}
    </label>
  );
}
