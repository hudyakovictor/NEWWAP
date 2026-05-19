import React from 'react';
import type { EvidenceResult } from '../../types/api';

interface VerdictPanelProps {
  evidence: EvidenceResult | null;
}

export const VerdictPanel: React.FC<VerdictPanelProps> = ({ evidence }) => {
  if (!evidence) {
    return (
      <div className="verdict-panel text-center flex flex-col gap-4 border p-4 bg-gray-800">
        <p className="text-gray-400">Select two photos to analyze</p>
      </div>
    );
  }

  const { posteriors, geometric, texture, zone_deltas } = evidence;
  const h0 = posteriors?.H0 ?? 0;
  const h1 = posteriors?.H1 ?? 0;
  const h2 = posteriors?.H2 ?? 0;

  const topZones = zone_deltas
    ? Object.entries(zone_deltas)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
    : [];

  return (
    <div className="verdict-panel text-center flex flex-col gap-4 border p-4 bg-gray-800">
      <h2 className="text-2xl font-bold">
        Verdict: <span className="text-red-500">{evidence.verdict || '—'}</span>
      </h2>

      <div className="probabilities">
        <div>H0 (Same Person): {(h0 * 100).toFixed(1)}%</div>
        <div>H1 (Synthetic/Mask): {(h1 * 100).toFixed(1)}%</div>
        <div>H2 (Different Person): {(h2 * 100).toFixed(1)}%</div>
      </div>

      {texture?.h1_subtype && h1 > 0.5 && (
        <div className="h1-subtype mt-4 p-2 bg-gray-700 text-white">
          <p>Fake Type: {texture.h1_subtype.primary}</p>
          <p>Confidence: {texture.h1_subtype.confidence.toFixed(2)}</p>
        </div>
      )}

      <div className="metrics">
        <p>Geometric SNR: {(geometric?.snr ?? 0).toFixed(2)}</p>
        <p>Anomalies Flagged: {geometric?.anomalies_flagged ?? 0}</p>
      </div>

      {topZones.length > 0 && (
        <div className="zone-deltas mt-4">
          <h3 className="text-sm font-bold mb-2">Top Zone Deltas</h3>
          <ul className="text-xs text-left">
            {topZones.map(([zone, delta]) => (
              <li key={zone}>
                {zone}: {delta.toFixed(3)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
