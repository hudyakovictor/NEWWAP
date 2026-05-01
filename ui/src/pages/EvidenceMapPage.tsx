/**
 * Evidence Map page — central overview of platform readiness.
 *
 * Shows every module's evidence level, artifact provenance, and what
 * pipeline step is needed to upgrade.  This is the single place where
 * the owner can see at a glance how much of the platform is real data
 * vs stub.
 */

import { Page, PanelCard } from "../components/common/Page";
import { EvidenceBadge, type EvidenceLevel } from "../components/common/EvidenceStatus";
import {
  MODULE_EVIDENCE,
  evidenceSummary,
  readinessScore,
  type ModuleEvidence,
} from "../data/evidencePolicy";
import {
  ARTIFACT_MANIFEST,
  artifactCounts,
  type ArtifactEntry,
} from "../data/artifactManifest";

const LEVEL_ORDER: EvidenceLevel[] = ["real", "partial", "stub", "insufficient", "pending"];

function scoreColor(score: number): string {
  if (score >= 80) return "#22c55e";
  if (score >= 50) return "#f59e0b";
  return "#ef4444";
}

export default function EvidenceMapPage() {
  const summary = evidenceSummary();
  const score = readinessScore();
  const counts = artifactCounts();

  // Merge evidence + manifest by id
  const merged = MODULE_EVIDENCE.map((m) => {
    const artifact = ARTIFACT_MANIFEST.find((a) => a.id === m.id);
    return { ...m, artifact };
  });

  const byLevel = LEVEL_ORDER.filter((l) => summary[l] > 0).map((level) => ({
    level,
    modules: merged.filter((m) => m.level === level),
  }));

  return (
    <Page
      title="Карта доказанности"
      subtitle="Обзор готовности платформы: какие данные реальные, какие заглушки, что нужно для перехода"
    >
      {/* Score + summary */}
      <div className="grid grid-cols-6 gap-3 mb-3">
        <PanelCard className="col-span-2">
          <div className="text-center">
            <div className="text-4xl font-black" style={{ color: scoreColor(score) }}>
              {score}
            </div>
            <div className="text-[11px] text-muted">из 100 · индекс готовности</div>
            <div className="text-[10px] text-muted mt-1">
              real=100 · partial=55 · stub=10 · pending=20
            </div>
          </div>
        </PanelCard>
        <PanelCard>
          <div className="text-2xl font-semibold text-ok">{summary.real}</div>
          <div className="text-[11px] text-muted">реальные модули</div>
        </PanelCard>
        <PanelCard>
          <div className="text-2xl font-semibold text-warn">{summary.partial}</div>
          <div className="text-[11px] text-muted">частично готовые</div>
        </PanelCard>
        <PanelCard>
          <div className="text-2xl font-semibold" style={{ color: "#6b7a90" }}>{summary.stub}</div>
          <div className="text-[11px] text-muted">заглушки</div>
        </PanelCard>
        <PanelCard>
          <div className="text-2xl font-semibold text-ok">{counts.real}</div>
          <div className="text-[11px] text-muted">из {counts.total} артефактов реальные</div>
        </PanelCard>
      </div>

      {/* Progress bar */}
      <PanelCard title="Распределение по уровню доказанности" className="mb-3">
        <div className="flex h-8 rounded overflow-hidden">
          {LEVEL_ORDER.filter((l) => summary[l] > 0).map((level) => {
            const pct = (summary[level] / MODULE_EVIDENCE.length) * 100;
            const colors: Record<EvidenceLevel, string> = {
              real: "#22c55e",
              partial: "#f59e0b",
              stub: "#6b7a90",
              insufficient: "#ef4444",
              pending: "#38bdf8",
            };
            return (
              <div
                key={level}
                style={{ width: `${pct}%`, background: colors[level] }}
                className="flex items-center justify-center text-[10px] font-bold text-black"
                title={`${summary[level]} модулей: ${level}`}
              >
                {summary[level]} {level}
              </div>
            );
          })}
        </div>
      </PanelCard>

      {/* Grouped by level */}
      {byLevel.map(({ level, modules }) => (
        <PanelCard
          key={level}
          title={levelTitle(level)}
          className="mb-3"
        >
          <div className="space-y-3">
            {modules.map((m) => (
              <ModuleCard key={m.id} module={m} artifact={m.artifact} />
            ))}
          </div>
        </PanelCard>
      ))}
    </Page>
  );
}

function levelTitle(level: EvidenceLevel): string {
  const titles: Record<EvidenceLevel, string> = {
    real: "Реальные данные — можно использовать как рабочий сигнал",
    partial: "Частично готово — использовать осторожно, не для финального вывода",
    stub: "Заглушки — нельзя цитировать как forensic-результат",
    insufficient: "Данных недостаточно — вывод запрещён",
    pending: "Ожидает расчёта — не ошибка и не отрицательный результат",
  };
  return titles[level];
}

function ModuleCard({
  module,
  artifact,
}: {
  module: ModuleEvidence;
  artifact: ArtifactEntry | undefined;
}) {
  return (
    <div className="bg-bg-deep/70 border border-line/60 rounded p-3">
      <div className="flex items-center gap-2 mb-2">
        <EvidenceBadge level={module.level} />
        <span className="text-sm font-semibold text-white">{module.label}</span>
        <span className="text-[10px] text-muted ml-auto">id: {module.id}</span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-[11px]">
        <div>
          <span className="text-muted">Реальная часть: </span>
          <span className="text-white">{module.realPart || "—"}</span>
        </div>
        <div>
          <span className="text-muted">Заглушка: </span>
          <span className="text-white">{module.stubPart || "—"}</span>
        </div>
        <div>
          <span className="text-muted">Для перехода: </span>
          <span className="text-info">{module.upgradeHint}</span>
        </div>
        <div>
          <span className="text-muted">Страницы: </span>
          <span className="text-white">{module.pages.join(", ")}</span>
        </div>
      </div>

      {artifact && (
        <div className="mt-2 pt-2 border-t border-line/40 grid grid-cols-4 gap-2 text-[10px]">
          <div>
            <span className="text-muted">Стадия: </span>
            <span className="text-white">{artifact.pipelineStage}</span>
          </div>
          <div>
            <span className="text-muted">Дата расчёта: </span>
            <span className="text-white">{artifact.computedAt}</span>
          </div>
          <div>
            <span className="text-muted">Модель: </span>
            <span className="text-white">{artifact.modelVersion}</span>
          </div>
          <div>
            <span className="text-muted">Записей: </span>
            <span className="text-white">{artifact.recordCount}</span>
          </div>
        </div>
      )}
    </div>
  );
}
