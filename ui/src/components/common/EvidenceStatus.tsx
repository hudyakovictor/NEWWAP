import React from "react";

export type EvidenceLevel = "real" | "partial" | "stub" | "insufficient" | "pending";

const LEVELS: Record<EvidenceLevel, { label: string; color: string; title: string; description: string }> = {
  real: {
    label: "реальные данные",
    color: "#22c55e",
    title: "Можно использовать как рабочий сигнал",
    description: "Значение получено из реального файла, backend API или воспроизводимого отчёта. Его всё равно нужно проверять контекстом, но это не заглушка.",
  },
  partial: {
    label: "частично готово",
    color: "#f59e0b",
    title: "Использовать осторожно",
    description: "Часть входных данных реальная, но расчёт ещё не покрывает весь forensic-контракт. Подходит для навигации и диагностики, не для финального вывода.",
  },
  stub: {
    label: "заглушка",
    color: "#6b7a90",
    title: "Не является доказательством",
    description: "Значение оставлено как интерфейсный или совместимый mock-слой. Его нельзя цитировать как forensic-результат.",
  },
  insufficient: {
    label: "данных недостаточно",
    color: "#ef4444",
    title: "Вывод запрещён",
    description: "Backend явно сообщил, что признаков недостаточно. Нужно сначала завершить соответствующую стадию обработки.",
  },
  pending: {
    label: "ожидает расчёта",
    color: "#38bdf8",
    title: "Стадия ещё не запускалась или не завершена",
    description: "Это не ошибка и не отрицательный результат. Данные появятся после прогона pipeline.",
  },
};

export function EvidenceBadge({ level, className = "" }: { level: EvidenceLevel; className?: string }) {
  const cfg = LEVELS[level];
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-[10px] font-semibold ${className}`}
      style={{ color: cfg.color, background: cfg.color + "20", border: `1px solid ${cfg.color}55` }}
      title={`${cfg.title}: ${cfg.description}`}
    >
      {cfg.label}
    </span>
  );
}

export function EvidenceNote({
  level,
  children,
  className = "",
}: {
  level: EvidenceLevel;
  children?: React.ReactNode;
  className?: string;
}) {
  const cfg = LEVELS[level];
  return (
    <div
      className={`rounded border p-3 text-[11px] leading-relaxed ${className}`}
      style={{ color: cfg.color, background: cfg.color + "12", borderColor: cfg.color + "55" }}
    >
      <div className="mb-1 flex items-center gap-2">
        <EvidenceBadge level={level} />
        <span className="font-semibold text-white">{cfg.title}</span>
      </div>
      <div>{children ?? cfg.description}</div>
    </div>
  );
}
