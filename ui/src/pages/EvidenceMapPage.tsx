/**
 * Evidence Map page — simplified module overview
 */

import { Page, PanelCard } from "../components/common/Page";
import { MODULE_EVIDENCE } from "../data/evidencePolicy";

export default function EvidenceMapPage() {
  return (
    <Page
      title="Карта доказанности"
      subtitle="Обзор модулей платформы"
    >
      <PanelCard title={`Модули (${MODULE_EVIDENCE.length})`}>
        <div className="space-y-2">
          {MODULE_EVIDENCE.map((m) => (
            <div key={m.id} className="bg-bg-deep/70 border border-line/60 rounded p-2 flex items-center gap-2">
              <span className="text-sm font-semibold text-white">{m.label}</span>
              <span className="text-[10px] text-muted ml-auto">id: {m.id}</span>
              <span className="text-[10px] text-muted">{m.pages.join(", ")}</span>
            </div>
          ))}
        </div>
      </PanelCard>
    </Page>
  );
}
