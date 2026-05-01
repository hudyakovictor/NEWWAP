import { useEffect, useMemo, useRef, useState } from "react";
import { useApp } from "../../store/appStore";
import type { PageId } from "../TopBar";
import { PHOTOS } from "../../mock/photos";

interface Cmd {
  id: string;
  label: string;
  hint?: string;
  group: "nav" | "photo" | "action";
  run(): void;
}

export default function CommandPalette() {
  const { setPage } = useApp();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
        setQuery("");
        setActiveIdx(0);
      } else if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 10);
  }, [open]);

  const navCommands: Cmd[] = useMemo(() => {
    const pages: Array<{ id: PageId; label: string; hint?: string }> = [
      { id: "photos", label: "Фотоархив" },
      { id: "clusters", label: "Визуальные кластеры" },
      { id: "signals", label: "Сигналы", hint: "реальные фото" },
      { id: "timeline", label: "Таймлайн", hint: "главная" },
      { id: "pairs", label: "Анализ пары" },
      { id: "matrix", label: "Матрица N×N" },
      { id: "iterations", label: "Итерации" },
      { id: "anomalies", label: "Аномалии" },
      { id: "ageing", label: "Кривая старения" },
      { id: "calibration", label: "Калибровка" },
      { id: "progress", label: "Прогресс", hint: "real vs stub" },
      { id: "pipeline", label: "Пайплайн" },
      { id: "jobs", label: "Задачи" },
      { id: "investigations", label: "Кейсы" },
      { id: "diary", label: "Дневник" },
      { id: "report_builder", label: "Конструктор отчётов" },
      { id: "settings", label: "Настройки" },
      { id: "audit", label: "Аудит", hint: "автономный" },
      { id: "logs", label: "Логи" },
      { id: "evidence_map", label: "Карта доказанности", hint: "готовность платформы" },
    ];
    return pages.map((p) => ({
      id: `nav-${p.id}`,
      label: p.label,
      hint: p.hint,
      group: "nav",
      run: () => {
        setPage(p.id as PageId);
        setOpen(false);
      },
    }));
  }, [setPage]);

  const photoCommands: Cmd[] = useMemo(
    () =>
      PHOTOS.slice(0, 300).map((p) => ({
        id: `photo-${p.id}`,
        label: `Photo ${p.date} — ${p.pose}`,
        hint: p.cluster ?? undefined,
        group: "photo",
        run: () => {
          // Hop to photos page with the photo pre-opened via focus state not supported,
          // so we just navigate to photos. Follow-up: pass a `focusPhotoId` via store.
          setPage("photos");
          setOpen(false);
        },
      })),
    [setPage]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const all = [...navCommands, ...photoCommands];
    if (!q) return navCommands;
    return all.filter((c) => c.label.toLowerCase().includes(q) || (c.hint ?? "").toLowerCase().includes(q)).slice(0, 80);
  }, [query, navCommands, photoCommands]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] bg-black/60 flex items-start justify-center pt-32"
      onClick={() => setOpen(false)}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl bg-bg-panel border border-line rounded-lg shadow-2xl overflow-hidden"
      >
        <div className="p-2 border-b border-line">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIdx(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActiveIdx((i) => Math.min(filtered.length - 1, i + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActiveIdx((i) => Math.max(0, i - 1));
              } else if (e.key === "Enter") {
                e.preventDefault();
                filtered[activeIdx]?.run();
              }
            }}
            placeholder="Поиск по навигации, фото, действиям…"
            className="w-full h-9 px-3 bg-bg-deep border border-line rounded text-white text-[12px]"
          />
        </div>
        <div className="max-h-[50vh] overflow-auto">
          {filtered.length === 0 && (
            <div className="p-4 text-[11px] text-muted">Ничего не найдено для «{query}».</div>
          )}
          {filtered.map((c, i) => (
            <button
              key={c.id}
              onClick={() => c.run()}
              onMouseEnter={() => setActiveIdx(i)}
              className={`w-full text-left px-3 py-2 flex items-center gap-2 ${
                i === activeIdx ? "bg-line text-white" : "hover:bg-line/60 text-white"
              }`}
            >
              <span
                className={`text-[9px] px-1.5 py-0.5 rounded ${
                  c.group === "nav" ? "bg-info/30 text-info" : c.group === "photo" ? "bg-accent/30 text-accent" : "bg-warn/30 text-warn"
                }`}
              >
                {c.group}
              </span>
              <span className="text-[12px] flex-1 truncate">{c.label}</span>
              {c.hint && <span className="text-[10px] text-muted">{c.hint}</span>}
            </button>
          ))}
        </div>
        <div className="flex items-center justify-between px-3 py-1.5 border-t border-line text-[10px] text-muted">
          <span>↑↓ навигация · ↵ открыть · esc закрыть</span>
          <span>⌘/Ctrl+K</span>
        </div>
      </div>
    </div>
  );
}
