export type PageId =
  | "timeline"
  | "photos"
  | "pairs"
  | "comparison"
  | "matrix"
  | "ageing"
  | "anomalies"
  | "iterations"
  | "calibration"
  | "pipeline"
  | "jobs"
  | "investigations"
  | "diary"
  | "report_builder"
  | "settings"
  | "signals"
  | "progress"
  | "clusters"
  | "audit"
  | "logs"
  | "evidence_map"
  | "upload";

const MENU_GROUPS: { title: string; items: { id: PageId; label: string }[] }[] = [
  {
    title: "Фотоархив",
    items: [
      { id: "photos", label: "Фото" },
      { id: "clusters", label: "Кластеры" },
      { id: "signals", label: "Сигналы" },
    ],
  },
  {
    title: "Анализ",
    items: [
      { id: "timeline", label: "Таймлайн" },
      { id: "pairs", label: "Пара" },
      { id: "comparison", label: "Сравнение" },
      { id: "matrix", label: "Матрица" },
      { id: "iterations", label: "Итерации" },
      { id: "anomalies", label: "Аномалии" },
      { id: "ageing", label: "Возраст" },
    ],
  },
  {
    title: "Калибровка",
    items: [
      { id: "calibration", label: "Бакеты" },
      { id: "progress", label: "Прогресс" },
      { id: "evidence_map", label: "Карта доказанности" },
    ],
  },
  {
    title: "Конвейер",
    items: [
      { id: "pipeline", label: "Пайплайн" },
      { id: "jobs", label: "Задачи" },
      { id: "investigations", label: "Кейсы" },
      { id: "diary", label: "Дневник" },
    ],
  },
  {
    title: "Отчёты",
    items: [
      { id: "report_builder", label: "Конструктор" },
      { id: "settings", label: "Настройки" },
    ],
  },
  {
    title: "Диагностика",
    items: [
      { id: "audit", label: "Аудит" },
      { id: "logs", label: "Логи" },
    ],
  },
];

import { useEffect, useState } from "react";
import { subscribeAudit } from "../debug/auditLoop";
import type { AuditReport } from "../debug/audit";

export default function TopBar({
  current,
  onNav,
}: {
  current: PageId;
  onNav: (p: PageId) => void;
}) {
  const [audit, setAudit] = useState<AuditReport | null>(null);
  useEffect(() => subscribeAudit(setAudit), []);
  return (
    <header className="flex items-center h-11 px-3 bg-bg-deep border-b border-line select-none shrink-0">
      <button
        onClick={() => onNav("timeline")}
        className="flex items-center gap-2 pr-4 border-r border-line mr-4"
      >
        <div className="w-6 h-6 rounded-md bg-gradient-to-br from-accent to-info grid place-items-center text-[10px] font-bold text-white">
          DP
        </div>
        <div className="flex flex-col leading-tight text-left">
          <span className="text-xs font-semibold text-white tracking-wide">DEEPUTIN</span>
          <span className="text-[10px] text-muted -mt-0.5">расследование · 1999–2025</span>
        </div>
      </button>

      <nav className="flex items-center gap-3 overflow-auto">
        {MENU_GROUPS.map((g) => (
          <div key={g.title} className="flex items-center gap-1">
            <span className="text-[9px] uppercase tracking-wider text-muted px-1 border-r border-line/60 pr-2 mr-1">
              {g.title}
            </span>
            {g.items.map((m) => (
              <button
                key={m.id}
                onClick={() => onNav(m.id)}
                className={`px-2 h-7 rounded-md text-[11px] whitespace-nowrap transition-colors ${
                  current === m.id
                    ? "bg-line text-white"
                    : "text-muted hover:text-white hover:bg-line/60"
                }`}
              >
                {m.label}
              </button>
            ))}
          </div>
        ))}
      </nav>

      <div className="ml-auto flex items-center gap-2 text-[11px] text-muted shrink-0">
        <button
          onClick={() => onNav("upload")}
          className="px-3 py-1.5 rounded-lg bg-accent/80 hover:bg-accent transition-all text-[11px] font-medium text-white shadow-lg shadow-accent/20 flex items-center gap-1.5"
          title="Добавить фото в анализ"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Добавить фото
        </button>
        <button
          onClick={async () => {
            if (confirm("Вы уверены, что хотите очистить все данные?")) {
              try {
                const response = await fetch("/api/reset-all", { method: "POST" });
                if (response.ok) {
                  localStorage.clear();
                  sessionStorage.clear();
                  window.location.reload();
                } else {
                  alert("Не удалось очистить данные. Сервер вернул ошибку.");
                }
              } catch (error) {
                console.error("Failed to reset:", error);
                alert("Не удалось очистить данные. Проверьте соединение с сервером.");
              }
            }
          }}
          className="px-2 py-1 rounded bg-danger/20 hover:bg-danger/40 text-[10px] text-danger border border-danger/30"
          title="Очистить все данные и сделать готовым для нового анализа"
        >
          Очистить все данные
        </button>
        <button
          onClick={() => onNav("audit")}
          className="px-2 py-1 rounded text-[10px] border border-line/60 hover:bg-line/40"
          title="Нажмите для полного отчёта аудита"
        >
          {audit ? (
            audit.counts.danger > 0 ? (
              <span className="text-danger font-semibold">⚠ {audit.counts.danger}d / {audit.counts.warn}w</span>
            ) : audit.counts.warn > 0 ? (
              <span className="text-warn">⚠ {audit.counts.warn}w / {audit.counts.info}i</span>
            ) : audit.counts.total > 0 ? (
              <span className="text-info">ℹ {audit.counts.info}</span>
            ) : (
              <span className="text-ok">✓ green</span>
            )
          ) : (
            <span className="text-muted">audit…</span>
          )}
        </button>
        <span className="px-2 py-1 rounded border border-line text-muted text-[10px]">⌘K</span>
      </div>
    </header>
  );
}
