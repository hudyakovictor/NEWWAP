import React, { useRef } from 'react';
import type { EvidenceResult } from '../types/api';

interface MatrixProps {
  photoIds: string[];
  matrix: number[][];
  onCellClick?: (i: number, j: number, evidence: EvidenceResult | null) => void;
  clusters?: Record<string, string>;
}

export const MatrixTable: React.FC<MatrixProps> = ({ photoIds, matrix, onCellClick, clusters }) => {
  const evidenceCache = useRef<Record<string, EvidenceResult>>({});

  if (photoIds.length !== matrix.length) {
    console.error('MatrixTable: photoIds and matrix length mismatch');
    return null;
  }

  const handleCellClick = async (i: number, j: number) => {
    const cacheKey = `${photoIds[i]}_${photoIds[j]}`;
    if (evidenceCache.current[cacheKey]) {
      onCellClick?.(i, j, evidenceCache.current[cacheKey]);
      return;
    }

    try {
      const res = await fetch('/api/evidence/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id_a: photoIds[i], photo_id_b: photoIds[j] })
      });
      const data: EvidenceResult = await res.json();
      evidenceCache.current[cacheKey] = data;
      onCellClick?.(i, j, data);
    } catch (err) {
      console.error('Failed to fetch evidence:', err);
      onCellClick?.(i, j, null);
    }
  };

  // Функция для цвета ячейки: зеленая - один человек, красная - разные
  const getCellColor = (value: number) => {
    if (isNaN(value) || value === undefined) return '#333'; // Ошибка / нет данных
    const green = Math.round(value * 255);
    const red = Math.round((1 - value) * 255);
    return `rgba(${red}, ${green}, 0, 0.6)`;
  };

  return (
    <div className="overflow-auto max-w-full">
      <table className="table-auto border-collapse border border-gray-500 text-xs">
        <thead>
          <tr>
            <th className="border p-2 bg-gray-800">ID</th>
            {photoIds.map(id => (
              <th key={id} className="border p-2 w-16 truncate" title={id}>{id.substring(0,6)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={`row-${i}`}>
              <th className="border p-2 bg-gray-800 truncate w-16" title={photoIds[i]}>
                {photoIds[i].substring(0,6)}
              </th>
              {row.map((val, j) => (
                <td
                  key={`cell-${i}-${j}`}
                  className="border p-4 text-center cursor-help"
                  style={{
                    backgroundColor: getCellColor(val),
                    border: clusters && clusters[photoIds[i]] ? `2px solid ${clusters[photoIds[i]]}` : undefined
                  }}
                  title={`${photoIds[i]} vs ${photoIds[j]}: ${(val * 100).toFixed(1)}%`}
                  onClick={() => handleCellClick(i, j)}
                >
                  {(val * 100).toFixed(0)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {clusters && Object.keys(clusters).length > 0 && (
        <div className="cluster-legend mt-4 flex flex-wrap gap-2">
          {Object.entries(clusters).map(([photoId, color]) => (
            <div key={photoId} className="flex items-center gap-1 text-xs text-gray-400">
              <div className="w-3 h-3 rounded" style={{ backgroundColor: color }} />
              <span>{photoId.substring(0, 6)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
