import { useEffect, useState } from "react";
import { Page, PanelCard } from "../components/common/Page";
import { api, type PipelineStage, type CacheSummary } from "../api";
import { EvidenceBadge, EvidenceNote } from "../components/common/EvidenceStatus";

export default function PipelinePage() {
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [cache, setCache] = useState<CacheSummary | null>(null);
  const [showCache, setShowCache] = useState(false);

  useEffect(() => {
    api.getPipelineStages().then(setStages);
    api.getCacheSummary().then(setCache);
  }, []);

  if (!stages.length) {
    return <Page title="Пайплайн"><div className="text-[11px] text-muted">Загрузка…</div></Page>;
  }

  const totalFailed = stages.reduce((a, s) => a + s.failed, 0);
  const totalTime = stages.reduce((a, s) => a + s.avgMs, 0);
  const maxGPU = Math.max(...stages.map((s) => s.gpuMemoryMB ?? 0));

  return (
    <Page
      title="Пайплайн"
      subtitle="Стадии обработки: пропускная способность, ошибки, ресурсы"
      actions={
        <button
          disabled={totalFailed === 0}
          title={totalFailed === 0 ? "Ошибок нет; непосчитанные стадии отображаются как pending в примечаниях." : "Перезапуск серверной очереди ошибок"}
          className="px-3 h-8 rounded bg-accent/70 hover:bg-accent text-[11px] text-white disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Перезапустить ошибки
        </button>
      }
    >
      <div className="grid grid-cols-4 gap-3 mb-3">
        <Stat label="стадий" value={String(stages.length)} color="#38bdf8" />
        <Stat label="всего ошибок" value={String(totalFailed)} color={totalFailed > 0 ? "#ef4444" : "#22c55e"} />
        <Stat label="ср. время на фото" value={`${totalTime} мс`} color="#a855f7" />
        <Stat label="пик GPU" value={`${maxGPU} МБ`} color="#22c55e" />
      </div>

      <EvidenceNote level="partial" className="mb-3">
        Важно: «ошибки» — это реальные сбои стадии. Непосчитанные downstream-этапы показываются в примечаниях как pending
        и не считаются forensic-провалом.
      </EvidenceNote>

      <PanelCard title="Поток стадий" className="mb-3">
        <div className="flex gap-2 overflow-auto pb-2">
          {stages.map((s, i) => {
            const dropPct =
              i === 0
                ? 0
                : ((stages[i - 1].outputCount - s.outputCount) / (stages[i - 1].outputCount || 1)) * 100;
            return (
              <div key={s.id} className="flex items-center gap-2 shrink-0">
                <div
                  className={`w-48 rounded border p-2 ${
                    s.failed > 0 ? "border-warn/70 bg-warn/10" : "border-line bg-bg-deep"
                  }`}
                >
                  <div className="text-[10px] text-muted">#{s.order}</div>
                  <div className="text-[12px] font-semibold text-white leading-tight">{s.name}</div>
                  <div className="mt-1">
                    <EvidenceBadge level={s.outputCount === s.inputCount ? "real" : s.failed > 0 ? "partial" : "pending"} />
                  </div>
                  <div className="mt-1 grid grid-cols-2 gap-1 text-[10px]">
                    <div className="text-muted">вх.</div>
                    <div className="font-mono text-white">{s.inputCount}</div>
                    <div className="text-muted">вых.</div>
                    <div className="font-mono text-white">{s.outputCount}</div>
                    <div className="text-muted">ошиб.</div>
                    <div className={`font-mono ${s.failed > 0 ? "text-danger" : "text-muted"}`}>{s.failed}</div>
                    <div className="text-muted">ср.</div>
                    <div className="font-mono text-info">{s.avgMs} мс</div>
                    {s.gpuMemoryMB ? (
                      <>
                        <div className="text-muted">gpu</div>
                        <div className="font-mono text-accent">{s.gpuMemoryMB} МБ</div>
                      </>
                    ) : null}
                  </div>
                </div>
                {i < stages.length - 1 && (
                  <div className="flex flex-col items-center text-[10px]">
                    <span className={dropPct > 0 ? "text-warn" : "text-muted"}>
                      {dropPct > 0 ? `−${dropPct.toFixed(1)}%` : "→"}
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </PanelCard>

      <PanelCard title="Детали стадий">
        <table className="w-full text-[11px]">
          <thead className="text-muted border-b border-line">
            <tr>
              <th className="text-left p-2">#</th>
              <th className="text-left p-2">стадия</th>
              <th className="text-left p-2">вх.</th>
              <th className="text-left p-2">вых.</th>
              <th className="text-left p-2">ошибки</th>
              <th className="text-left p-2">ср. мс</th>
              <th className="text-left p-2">GPU МБ</th>
              <th className="text-left p-2">послед. ошибка</th>
              <th className="text-left p-2">примечания</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((s) => (
              <tr key={s.id} className="border-b border-line/40">
                <td className="p-2 text-muted">{s.order}</td>
                <td className="p-2 text-white">{s.name}</td>
                <td className="p-2 font-mono text-white">{s.inputCount}</td>
                <td className="p-2 font-mono text-white">{s.outputCount}</td>
                <td className={`p-2 font-mono ${s.failed > 0 ? "text-danger" : "text-muted"}`}>{s.failed}</td>
                <td className="p-2 font-mono text-info">{s.avgMs}</td>
                <td className="p-2 font-mono text-accent">{s.gpuMemoryMB ?? "—"}</td>
                <td className="p-2 text-warn">{s.lastError ?? ""}</td>
                <td className="p-2 text-muted">{s.notes ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PanelCard>

      {/* Cache section (merged from CachePage) */}
      <button
        onClick={() => setShowCache(!showCache)}
        className="mt-3 px-3 h-8 rounded bg-line/70 hover:bg-line text-[11px] text-white flex items-center gap-2"
      >
        <span className={`transition-transform ${showCache ? "rotate-180" : ""}`}>▼</span>
        {showCache ? "Свернуть кэш реконструкций" : "Кэш реконструкций (3DDFA_v3)"}
      </button>

      {showCache && cache && (
        <div className="mt-3 space-y-3">
          {(() => {
            const budgetUsage = cache.vramFootprintMB / cache.vramBudgetMB;
            return (
              <>
                <div className="grid grid-cols-4 gap-3">
                  <Stat label="записи" value={`${cache.currentSize}/${cache.maxSize}`} color="#38bdf8" />
                  <Stat label="VRAM занято" value={`${cache.vramFootprintMB} МБ`} color="#a855f7" />
                  <Stat label="VRAM бюджет" value={`${cache.vramBudgetMB} МБ`} color="#22c55e" />
                  <Stat label="утилизация" value={`${(budgetUsage * 100).toFixed(1)}%`} color={budgetUsage > 0.8 ? "#ef4444" : "#22c55e"} />
                </div>

                <PanelCard title="Бюджет VRAM">
                  <div className="h-3 bg-bg-deep rounded overflow-hidden">
                    <div
                      className="h-full"
                      style={{
                        width: `${Math.min(100, budgetUsage * 100)}%`,
                        background: budgetUsage > 0.8 ? "#ef4444" : budgetUsage > 0.6 ? "#f59e0b" : "#22c55e",
                      }}
                    />
                  </div>
                  <div className="text-[11px] text-muted mt-2">
                    Кэш освобождает VRAM при вытеснении. Блокировка новых реконструкций при остатке &lt;200 МБ.
                  </div>
                </PanelCard>

                <PanelCard title={`Записи (${cache.entries.length})`}>
                  <table className="w-full text-[11px]">
                    <thead className="text-muted border-b border-line">
                      <tr>
                        <th className="text-left p-2">md5</th>
                        <th className="text-left p-2">фото</th>
                        <th className="text-left p-2">год</th>
                        <th className="text-left p-2">нейтр.</th>
                        <th className="text-left p-2">VRAM</th>
                        <th className="text-left p-2">создано</th>
                        <th className="text-left p-2">посл. доступ</th>
                        <th className="text-left p-2">попадания</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cache.entries.map((e) => (
                        <tr key={e.md5} className="border-b border-line/30">
                          <td className="p-2 font-mono text-white truncate max-w-[200px]">{e.md5}</td>
                          <td className="p-2 font-mono text-muted">{e.photoId}</td>
                          <td className="p-2 font-mono text-white">{e.year}</td>
                          <td className="p-2">{e.neutral ? <span className="text-ok">да</span> : <span className="text-muted">нет</span>}</td>
                          <td className="p-2 font-mono text-white">{e.vramMB} МБ</td>
                          <td className="p-2 text-muted">{e.createdAt}</td>
                          <td className="p-2 text-muted">{e.lastAccess}</td>
                          <td className="p-2 font-mono text-info">{e.hits}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </PanelCard>

                <PanelCard title="История вытеснений">
                  <table className="w-full text-[11px]">
                    <thead className="text-muted border-b border-line">
                      <tr>
                        <th className="text-left p-2">md5</th>
                        <th className="text-left p-2">когда</th>
                        <th className="text-left p-2">причина</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cache.evictions.map((ev, i) => (
                        <tr key={i} className="border-b border-line/30">
                          <td className="p-2 font-mono text-muted">{ev.md5}</td>
                          <td className="p-2 text-muted">{ev.at}</td>
                          <td className={`p-2 ${ev.reason.includes("VRAM") ? "text-warn" : "text-muted"}`}>{ev.reason}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </PanelCard>
              </>
            );
          })()}
        </div>
      )}
    </Page>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <PanelCard>
      <div className="text-2xl font-semibold" style={{ color }}>{value}</div>
      <div className="text-[11px] text-muted">{label}</div>
    </PanelCard>
  );
}
