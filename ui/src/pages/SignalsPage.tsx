import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { loadSignalReportForUi } from "../debug/invariants_signals";
import { EvidenceBadge } from "../components/common/EvidenceStatus";
import { evidenceOf } from "../data/evidencePolicy";

interface SlimSignal {
  file: string;
  url: string;
  bytes: number;
  sha256: string;
  width?: number;
  height?: number;
  format: string;
  dhash?: string;
  avgLuminance?: number;
}
interface SlimReport {
  generatedAt: string;
  count: number;
  entries: SlimSignal[];
  duplicates: Array<{ sha256: string; files: string[] }>;
  closestDhashPairs?: Array<{ a: string; b: string; distance: number }>;
}

function hammingHex(a: string, b: string): number {
  let d = 0;
  for (let i = 0; i < a.length; i += 2) {
    const x = parseInt(a.slice(i, i + 2), 16) ^ parseInt(b.slice(i, i + 2), 16);
    let v = x;
    v = v - ((v >> 1) & 0x55);
    v = (v & 0x33) + ((v >> 2) & 0x33);
    v = (v + (v >> 4)) & 0x0f;
    d += v;
  }
  return d;
}

function dhashColor(distance: number): string {
  // 0 → green (identical), 12 → yellow, 24+ → red
  if (distance < 4) return "#22c55e";
  if (distance < 8) return "#86efac";
  if (distance < 12) return "#fde047";
  if (distance < 16) return "#f59e0b";
  if (distance < 20) return "#fb923c";
  return "#ef4444";
}

export default function SignalsPage() {
  const [report, setReport] = useState<SlimReport | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    loadSignalReportForUi().then((r) => {
      if (!r) setMissing(true);
      else setReport(r as SlimReport);
    });
  }, []);

  if (missing) {
    return (
      <Page title="Сигналы реальных фото">
        <PanelCard title="Нет отчёта сигналов на диске">
          <div className="text-[11px] text-muted">
            Запустите <code className="text-white">npm run signals</code> из <code className="text-white">ui/</code>.
            Скрипт сканирует все JPEG/PNG в <code className="text-white">public/photos/</code> и записывает
            <code className="text-white"> signal-report.json</code> + компактную копию в <code className="text-white">public/</code>.
          </div>
        </PanelCard>
      </Page>
    );
  }
  if (!report) return <Page title="Сигналы реальных фото"><div className="text-[11px] text-muted">Загрузка…</div></Page>;

  const totalBytes = report.entries.reduce((a, e) => a + e.bytes, 0);
  const formats = report.entries.reduce<Record<string, number>>((a, e) => {
    a[e.format] = (a[e.format] ?? 0) + 1;
    return a;
  }, {});
  const dimGroups = report.entries.reduce<Record<string, number>>((a, e) => {
    const k = e.width && e.height ? `${e.width}×${e.height}` : "unknown";
    a[k] = (a[k] ?? 0) + 1;
    return a;
  }, {});

  return (
    <Page
      title="Сигналы реальных фото"
      subtitle={`${report.count} файлов · ${(totalBytes / 1024).toFixed(0)} КБ · сгенерировано ${report.generatedAt}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <EvidenceBadge level={evidenceOf("signals")!.level} />
        <span className="text-[11px] text-muted">Все данные на этой странице — реальные результаты сканирования фото</span>
      </div>
      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="файлы"      value={report.count}                                        color="#cfd8e6" />
        <Stat label="уникальных SHA" value={new Set(report.entries.map((e) => e.sha256)).size}   color={report.duplicates.length ? "#ef4444" : "#22c55e"} />
        <Stat label="дубликаты" value={report.duplicates.length}                            color={report.duplicates.length ? "#ef4444" : "#22c55e"} />
        <Stat label="всего КБ"   value={(totalBytes / 1024).toFixed(0)}                       color="#a855f7" />
      </div>

      <PanelCard title="Формат и размеры" className="mb-3">
        <div className="grid grid-cols-2 gap-3 text-[11px]">
          <div>
            <div className="text-muted uppercase tracking-widest text-[10px] mb-1">формат</div>
            {Object.entries(formats).map(([k, n]) => (
              <KV key={k} k={k} v={n} />
            ))}
          </div>
          <div>
            <div className="text-muted uppercase tracking-widest text-[10px] mb-1">размеры</div>
            {Object.entries(dimGroups).map(([k, n]) => (
              <KV key={k} k={k} v={n} />
            ))}
          </div>
        </div>
      </PanelCard>

      {report.duplicates.length > 0 && (
        <PanelCard title="Дубликаты по хешу" className="mb-3">
          <ul className="text-[11px] space-y-1">
            {report.duplicates.map((d) => (
              <li key={d.sha256} className="text-warn">
                <span className="font-mono">{d.sha256.slice(0, 16)}…</span> ·{" "}
                <span className="text-white">{d.files.join(", ")}</span>
              </li>
            ))}
          </ul>
        </PanelCard>
      )}

      {report.closestDhashPairs && report.closestDhashPairs.length > 0 && (
        <PanelCard title="Ближайшие dHash-пары (перцептивное сходство)" className="mb-3">
          <div className="text-[11px] text-muted mb-2">
            Меньшее расстояние Хэмминга = большее визуальное сходство. Для портретов одного человека
            типичное расстояние 12–22; менее 4 означает почти дубликат (одинаковое содержание).
          </div>
          <table className="w-full text-[11px]">
            <thead className="text-muted border-b border-line">
              <tr>
                <th className="text-left p-2 w-16">расстояние</th>
                <th className="text-left p-2">фото A</th>
                <th className="text-left p-2">фото B</th>
              </tr>
            </thead>
            <tbody>
              {report.closestDhashPairs.slice(0, 15).map((p) => (
                <tr key={`${p.a}-${p.b}`} className="border-b border-line/30">
                  <td className="p-2">
                    <span
                      className="font-mono px-2 py-0.5 rounded text-black font-semibold"
                      style={{ background: dhashColor(p.distance) }}
                    >
                      {p.distance}
                    </span>
                  </td>
                  <td className="p-2 flex items-center gap-2">
                    <img src={`/photos/${p.a}`} alt="" className="w-8 h-8 rounded object-cover border border-line" />
                    <span className="font-mono text-white">{p.a}</span>
                  </td>
                  <td className="p-2 flex items-center gap-2">
                    <img src={`/photos/${p.b}`} alt="" className="w-8 h-8 rounded object-cover border border-line" />
                    <span className="font-mono text-white">{p.b}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </PanelCard>
      )}

      {/* Heatmap N×N (only if we have dhash) */}
      {report.entries.some((e) => e.dhash) && (
        <PanelCard title="Тепловая карта попарных dHash-расстояний" className="mb-3">
          <DhashHeatmap entries={report.entries.filter((e) => e.dhash) as Array<SlimSignal & { dhash: string }>} />
        </PanelCard>
      )}

      <PanelCard title="Сигналы по файлам">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">превью</th>
              <th className="text-left p-2">файл</th>
              <th className="text-left p-2">формат</th>
              <th className="text-left p-2">разм.</th>
              <th className="text-left p-2">объём</th>
              <th className="text-left p-2">ярк.</th>
              <th className="text-left p-2">dhash</th>
              <th className="text-left p-2">sha256</th>
            </tr>
          </thead>
          <tbody>
            {report.entries.map((e) => (
              <tr key={e.file} className="border-b border-line/30">
                <td className="p-1">
                  <img
                    src={e.url}
                    alt=""
                    className="w-12 h-12 object-cover rounded border border-line"
                    loading="lazy"
                  />
                </td>
                <td className="p-2 font-mono text-white">{e.file}</td>
                <td className="p-2 uppercase text-info">{e.format}</td>
                <td className="p-2 font-mono text-muted">
                  {e.width && e.height ? `${e.width}×${e.height}` : "—"}
                </td>
                <td className="p-2 font-mono text-muted">{(e.bytes / 1024).toFixed(1)} KB</td>
                <td className="p-2 font-mono text-muted">{e.avgLuminance ?? "—"}</td>
                <td className="p-2 font-mono text-info">{e.dhash ?? "—"}</td>
                <td className="p-2 font-mono text-muted">{e.sha256.slice(0, 16)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>
    </Page>
  );
}

function DhashHeatmap({ entries }: { entries: Array<SlimSignal & { dhash: string }> }) {
  // Build full distance matrix
  const matrix: number[][] = entries.map((a) =>
    entries.map((b) => (a === b ? 0 : hammingHex(a.dhash, b.dhash)))
  );
  return (
    <div className="overflow-auto">
      <table className="text-[10px]">
        <thead>
          <tr>
            <th className="p-1"></th>
            {entries.map((e) => (
              <th key={e.file} className="p-1 align-bottom">
                <img src={e.url} alt="" className="w-7 h-7 rounded object-cover border border-line/60" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {entries.map((row, i) => (
            <tr key={row.file}>
              <th className="p-1 align-middle text-right">
                <div className="flex items-center gap-1 justify-end">
                  <span className="text-muted font-mono">{row.file.slice(0, 7)}</span>
                  <img src={row.url} alt="" className="w-7 h-7 rounded object-cover border border-line/60" />
                </div>
              </th>
              {entries.map((_, j) => {
                const v = matrix[i][j];
                return (
                  <td key={j} className="p-0.5">
                    <div
                      className="w-7 h-7 rounded text-[9px] font-mono text-black grid place-items-center font-semibold"
                      style={{ background: dhashColor(v) }}
                      title={`${entries[i].file} ↔ ${entries[j].file} = ${v}`}
                    >
                      {v}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: React.ReactNode; color: string }) {
  return (
    <div className="bg-bg-panel border border-line rounded p-2">
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </div>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-line/40 py-0.5">
      <span className="text-muted">{k}</span>
      <span className="font-mono text-white">{v}</span>
    </div>
  );
}
