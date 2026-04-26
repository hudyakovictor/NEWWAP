import { Page, PanelCard } from "../components/common/Page";

interface Report {
  id: string;
  title: string;
  subject: string;
  verdict: "H0" | "H1" | "H2";
  createdAt: string;
  photos: number;
  format: "pdf" | "json" | "html";
}

const REPORTS: Report[] = [
  { id: "r-001", title: "Full 1999–2025 investigation", subject: "Subject 1", verdict: "H1", createdAt: "2025-04-21", photos: 1742, format: "pdf" },
  { id: "r-002", title: "Cluster B audit (2015–2020)", subject: "Subject 1", verdict: "H1", createdAt: "2025-04-22", photos: 432, format: "html" },
  { id: "r-003", title: "Calibration coverage review", subject: "calibration", verdict: "H0", createdAt: "2025-04-23", photos: 1742, format: "json" },
  { id: "r-004", title: "2012 identity-swap case", subject: "Subject 1", verdict: "H1", createdAt: "2025-04-24", photos: 58, format: "pdf" },
];

export default function ReportsPage() {
  return (
    <Page
      title="Reports"
      subtitle="Export forensic findings in structured formats"
      actions={
        <button className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white">
          + New report
        </button>
      }
    >
      <PanelCard title="Saved reports">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">id</th>
              <th className="text-left p-2">title</th>
              <th className="text-left p-2">subject</th>
              <th className="text-left p-2">verdict</th>
              <th className="text-left p-2">photos</th>
              <th className="text-left p-2">created</th>
              <th className="text-left p-2">format</th>
              <th className="text-right p-2"></th>
            </tr>
          </thead>
          <tbody>
            {REPORTS.map((r) => (
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
                    Open
                  </button>
                  <button className="px-2 h-6 rounded bg-info/60 hover:bg-info text-[10px] text-white">
                    Export
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>
    </Page>
  );
}
