
import type { Severity } from "../../mock/data";

const base = "w-[14px] h-[14px] inline-block";

export function SeverityIcon({ s }: { s: Severity }) {
  if (s === "ok")
    return (
      <svg viewBox="0 0 16 16" className={base}>
        <circle cx="8" cy="8" r="7" fill="#052e16" stroke="#22c55e" />
        <path d="M4.5 8.3l2.2 2.2L11.5 5.6" stroke="#22c55e" strokeWidth="1.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  if (s === "info")
    return (
      <svg viewBox="0 0 16 16" className={base}>
        <circle cx="8" cy="8" r="7" fill="#082f49" stroke="#38bdf8" />
        <path d="M8 7v4" stroke="#38bdf8" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="8" cy="5" r="0.9" fill="#38bdf8" />
      </svg>
    );
  if (s === "warn")
    return (
      <svg viewBox="0 0 16 16" className={base}>
        <path d="M8 1.5l7 12.5H1L8 1.5z" fill="#2a1a06" stroke="#f59e0b" strokeLinejoin="round" />
        <path d="M8 6v4" stroke="#f59e0b" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="8" cy="12.2" r="0.9" fill="#f59e0b" />
      </svg>
    );
  return (
    <svg viewBox="0 0 16 16" className={base}>
      <path d="M8 1.5l7 12.5H1L8 1.5z" fill="#2a0a0a" stroke="#ef4444" strokeLinejoin="round" />
      <path d="M8 6v4" stroke="#ef4444" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="8" cy="12.2" r="0.9" fill="#ef4444" />
    </svg>
  );
}

export function EventIcon({ kind }: { kind: "calendar" | "info" | "warn" | "danger" | "ok" | "health" }) {
  switch (kind) {
    case "calendar":
      return (
        <svg viewBox="0 0 16 16" className="w-4 h-4">
          <rect x="2" y="3.5" width="12" height="10" rx="1.5" fill="#1f0f12" stroke="#a855f7" />
          <path d="M2 6.5h12" stroke="#a855f7" />
          <path d="M5 2v3M11 2v3" stroke="#a855f7" strokeLinecap="round" />
        </svg>
      );
    case "health":
      return (
        <svg viewBox="0 0 16 16" className="w-4 h-4">
          <circle cx="8" cy="8" r="7" fill="#082f49" stroke="#38bdf8" />
          <path d="M3 8h2.5l1.2-2.2 2 4 1.3-2.5H13" stroke="#38bdf8" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
        </svg>
      );
    case "ok":
      return <SeverityIcon s="ok" />;
    case "info":
      return <SeverityIcon s="info" />;
    case "warn":
      return <SeverityIcon s="warn" />;
    case "danger":
      return <SeverityIcon s="danger" />;
  }
}
