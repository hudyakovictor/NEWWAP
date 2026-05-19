import React, { useState } from 'react';
import { PhotoPicker } from '../components/compare/PhotoPicker';
import { PhotoCard } from '../components/compare/PhotoCard';
import { VerdictPanel } from '../components/compare/VerdictPanel';
import { MeshViewer } from '../components/3d/MeshViewer';
import { MatrixTable } from '../components/MatrixTable';
import type { EvidenceResult } from '../types/api';
import { Download } from 'lucide-react';

export const ComparePage: React.FC = () => {
  const [photoA, setPhotoA] = useState<string>('');
  const [photoB, setPhotoB] = useState<string>('');
  const [evidence, setEvidence] = useState<EvidenceResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [show3DA, setShow3DA] = useState(false);
  const [show3DB, setShow3DB] = useState(false);
  const [activeTab, setActiveTab] = useState<'compare' | 'matrix'>('compare');
  const [matrixPhotoIds, setMatrixPhotoIds] = useState<string[]>([]);
  const [matrixData, setMatrixData] = useState<number[][]>([]);
  const [heatmapModeA, setHeatmapModeA] = useState<'mesh' | 'heatmap' | 'wireframe'>('mesh');
  const [heatmapModeB, setHeatmapModeB] = useState<'mesh' | 'heatmap' | 'wireframe'>('mesh');
  const [maxDeltaA, setMaxDeltaA] = useState(5.0);
  const [maxDeltaB, setMaxDeltaB] = useState(5.0);
  const [compareError, setCompareError] = useState<string | null>(null);
  const [matrixError, setMatrixError] = useState<string | null>(null);

  const handleExport = () => {
    if (!evidence) return;
    const exportData = {
      photo_a: photoA,
      photo_b: photoB,
      verdict: evidence.verdict,
      posteriors: evidence.posteriors,
      geometric: evidence.geometric,
      texture: evidence.texture,
      zone_deltas: evidence.zone_deltas,
      timestamp: new Date().toISOString()
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `comparison_${photoA}_${photoB}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleCompare = async () => {
    if (!photoA || !photoB) return;
    setLoading(true);
    try {
      const res = await fetch('/api/evidence/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ photo_id_a: photoA, photo_id_b: photoB })
      });
      const data = await res.json();
      setEvidence(data);
      // TODO: zone_deltas contains ~15-25 zone-level values, not per-vertex data.
      // Requires real per-vertex delta from /api/mesh endpoint for proper heatmap visualization.
      // For now, disable vertex colors until backend provides per-vertex delta data.
      // if (data.zone_deltas) {
      //   const deltas = Object.values(data.zone_deltas) as number[];
      //   setVertexDeltas(deltas);
      // }
      setCompareError(null);
    } catch (err) {
      console.error('Failed to compare:', err);
      setCompareError(err instanceof Error ? err.message : 'Failed to compare photos');
    } finally {
      setLoading(false);
    }
  };

  const handleMatrixAnalyze = async () => {
    if (matrixPhotoIds.length < 2) return;
    try {
      const res = await fetch('/api/evidence/matrix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(matrixPhotoIds)
      });
      const data = await res.json();
      setMatrixData(data.matrix || []);
      setMatrixError(null);
    } catch (err) {
      console.error('Failed to analyze matrix:', err);
      setMatrixError(err instanceof Error ? err.message : 'Failed to analyze matrix');
    }
  };

  return (
    <div className="compare-container p-6">
      <div className="tabs flex gap-4 mb-6 border-b border-gray-700 pb-2">
        <button
          className={`px-4 py-2 ${activeTab === 'compare' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'}`}
          onClick={() => setActiveTab('compare')}
        >
          Compare
        </button>
        <button
          className={`px-4 py-2 ${activeTab === 'matrix' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'}`}
          onClick={() => setActiveTab('matrix')}
        >
          Matrix
        </button>
      </div>

      {activeTab === 'compare' && (
        <>
          <div className="controls grid grid-cols-2 gap-6 mb-8">
            <div>
              <h3 className="text-white mb-2">Photo A</h3>
              <PhotoPicker onSelect={setPhotoA} selectedId={photoA} />
            </div>
            <div>
              <h3 className="text-white mb-2">Photo B</h3>
              <PhotoPicker onSelect={setPhotoB} selectedId={photoB} />
            </div>
          </div>

          {compareError && (
            <div className="bg-red-600 text-white p-4 rounded mb-4">
              {compareError}
            </div>
          )}
          {matrixError && (
            <div className="bg-red-600 text-white p-4 rounded mb-4">
              {matrixError}
            </div>
          )}
          
          <div className="analyze-button flex justify-center mb-8 gap-4">
            <button
              onClick={handleCompare}
              disabled={!photoA || !photoB || loading}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-8 py-3 rounded"
            >
              {loading ? 'Analyzing...' : 'Analyze'}
            </button>
            {evidence && (
              <button
                onClick={handleExport}
                className="bg-green-600 hover:bg-green-500 text-white px-6 py-3 rounded flex items-center gap-2"
              >
                <Download size={16} />
                Export
              </button>
            )}
          </div>

          {evidence && (
            <div className="results-grid grid grid-cols-1 lg:grid-cols-3 gap-6">
              <div className="panel-a">
                <PhotoCard photoId={photoA} onToggle3D={() => setShow3DA(!show3DA)} />
                {show3DA && (
                  <div className="mt-4">
                    <div className="heatmap-controls flex gap-2 mb-2">
                      <button
                        onClick={() => setHeatmapModeA('mesh')}
                        className={`px-2 py-1 text-xs ${heatmapModeA === 'mesh' ? 'bg-blue-600' : 'bg-gray-700'}`}
                      >
                        Mesh
                      </button>
                      <button
                        onClick={() => setHeatmapModeA('heatmap')}
                        className={`px-2 py-1 text-xs ${heatmapModeA === 'heatmap' ? 'bg-blue-600' : 'bg-gray-700'}`}
                      >
                        Heatmap
                      </button>
                      <button
                        onClick={() => setHeatmapModeA('wireframe')}
                        className={`px-2 py-1 text-xs ${heatmapModeA === 'wireframe' ? 'bg-blue-600' : 'bg-gray-700'}`}
                      >
                        Wireframe
                      </button>
                    </div>
                    {heatmapModeA === 'heatmap' && (
                      <div className="heatmap-slider mb-2">
                        <label className="text-xs text-gray-400">Max Delta: {maxDeltaA.toFixed(1)}</label>
                        <input
                          type="range"
                          min="1.0"
                          max="20.0"
                          step="0.5"
                          value={maxDeltaA}
                          onChange={(e) => setMaxDeltaA(parseFloat(e.target.value))}
                          className="w-full"
                        />
                        <div className="flex justify-between text-xs text-gray-500">
                          <span>0</span>
                          <span>max</span>
                        </div>
                      </div>
                    )}
                    <div className="h-64">
                      <MeshViewer
                        dataset="main"
                        photoId={photoA}
                        vertexColors={undefined}
                        wireframe={heatmapModeA === 'wireframe'}
                      />
                    </div>
                  </div>
                )}
              </div>

              <VerdictPanel evidence={evidence} />

              <div className="panel-b">
                <PhotoCard photoId={photoB} onToggle3D={() => setShow3DB(!show3DB)} />
                {show3DB && (
                  <div className="mt-4">
                    <div className="heatmap-controls flex gap-2 mb-2">
                      <button
                        onClick={() => setHeatmapModeB('mesh')}
                        className={`px-2 py-1 text-xs ${heatmapModeB === 'mesh' ? 'bg-blue-600' : 'bg-gray-700'}`}
                      >
                        Mesh
                      </button>
                      <button
                        onClick={() => setHeatmapModeB('heatmap')}
                        className={`px-2 py-1 text-xs ${heatmapModeB === 'heatmap' ? 'bg-blue-600' : 'bg-gray-700'}`}
                      >
                        Heatmap
                      </button>
                      <button
                        onClick={() => setHeatmapModeB('wireframe')}
                        className={`px-2 py-1 text-xs ${heatmapModeB === 'wireframe' ? 'bg-blue-600' : 'bg-gray-700'}`}
                      >
                        Wireframe
                      </button>
                    </div>
                    {heatmapModeB === 'heatmap' && (
                      <div className="heatmap-slider mb-2">
                        <label className="text-xs text-gray-400">Max Delta: {maxDeltaB.toFixed(1)}</label>
                        <input
                          type="range"
                          min="1.0"
                          max="20.0"
                          step="0.5"
                          value={maxDeltaB}
                          onChange={(e) => setMaxDeltaB(parseFloat(e.target.value))}
                          className="w-full"
                        />
                        <div className="flex justify-between text-xs text-gray-500">
                          <span>0</span>
                          <span>max</span>
                        </div>
                      </div>
                    )}
                    <div className="h-64">
                      <MeshViewer
                        dataset="main"
                        photoId={photoB}
                        vertexColors={undefined}
                        wireframe={heatmapModeB === 'wireframe'}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {activeTab === 'matrix' && (
        <div className="matrix-tab">
          <div className="mb-4">
            <PhotoPicker onSelect={(id) => {
              if (id && !matrixPhotoIds.includes(id) && matrixPhotoIds.length < 10) {
                setMatrixPhotoIds([...matrixPhotoIds, id]);
              }
            }} />
            <div className="mt-2 flex gap-2">
              <button
                onClick={handleMatrixAnalyze}
                disabled={matrixPhotoIds.length < 2}
                className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-4 py-2 rounded"
              >
                Analyze Matrix
              </button>
              <button
                onClick={() => setMatrixPhotoIds([])}
                className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded"
              >
                Clear
              </button>
            </div>
            <div className="mt-2 text-gray-400 text-sm">
              Selected: {matrixPhotoIds.join(', ')} (max 10)
            </div>
          </div>
          {matrixData.length > 0 && (
            <MatrixTable 
              photoIds={matrixPhotoIds} 
              matrix={matrixData} 
              onCellClick={(i, j, evidence) => {
                console.log(`Cell clicked: ${i}, ${j}`, evidence);
              }}
            />
          )}
        </div>
      )}
    </div>
  );
};
