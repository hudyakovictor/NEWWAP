import React, { useState, useEffect } from 'react';
import type { CalibrationSummary, Recommendation } from '../types/calibration';

export const CalibrationPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'summary' | 'recommendations'>('summary');
  const [summary, setSummary] = useState<CalibrationSummary | null>(null);
  const [recs, setRecs] = useState<Recommendation[]>([]);

  // Загрузка данных при маунте
  useEffect(() => {
    fetch('/api/calibration/summary')
      .then(r => r.json())
      .then(setSummary)
      .catch(() => setSummary(null));
    fetch('/api/recommendations')
      .then(r => r.json())
      .then(setRecs)
      .catch(() => setRecs([]));
  }, []);

  // Обработчик ручного оверрайда
  const handleApplyOverride = async (photoId: string, calibPhotoId: string) => {
    try {
      const res = await fetch('/api/calibration/override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          photo_id: photoId,
          calibration_photo_id: calibPhotoId,
          reason: 'Manual correction from UI',
          author: 'admin'
        })
      });
      if (!res.ok) throw new Error('Failed to apply override');
      // Reload both summary and recommendations
      const [summaryData, recsData] = await Promise.all([
        fetch('/api/calibration/summary').then(r => r.json()),
        fetch('/api/recommendations').then(r => r.json())
      ]);
      setSummary(summaryData);
      setRecs(recsData || []);
    } catch (err) {
      console.error('Failed to apply override:', err);
    }
  };

  return (
    <div className="calibration-page p-6 max-w-6xl mx-auto text-white">
      <h1 className="text-3xl font-bold mb-6">Здоровье калибровки (Self-Healing DB)</h1>
      
      {/* Навигация */}
      <div className="tabs flex gap-4 border-b border-gray-700 mb-6 pb-2">
        <button 
          className={`px-4 py-2 ${activeTab === 'summary' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'}`}
          onClick={() => setActiveTab('summary')}
        >
          Обзор бакетов
        </button>
        <button 
          className={`px-4 py-2 ${activeTab === 'recommendations' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-gray-400'}`}
          onClick={() => setActiveTab('recommendations')}
        >
          Рекомендации ({recs.length})
        </button>
      </div>

      {/* Вкладка: Обзор */}
      {activeTab === 'summary' && (
        summary === null ? (
          <div className="text-center py-8 text-gray-400">
            Failed to load calibration summary
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-6">
            <div className="stat-card bg-gray-800 p-4 rounded border border-gray-700">
              <h3 className="text-gray-400 text-sm">Всего калибровочных фото</h3>
              <p className="text-3xl font-bold">{summary.total_calibration_photos || 0}</p>
            </div>
            <div className="stat-card bg-gray-800 p-4 rounded border border-gray-700">
              <h3 className="text-gray-400 text-sm">Покрытие бакетов (Позы)</h3>
              <p className="text-3xl font-bold text-green-400">
                {summary.covered_buckets && summary.total_buckets 
                  ? ((summary.covered_buckets / summary.total_buckets) * 100).toFixed(0) + '%'
                  : '0%'}
              </p>
            </div>
            <div className="stat-card bg-gray-800 p-4 rounded border border-gray-700">
              <h3 className="text-gray-400 text-sm">Ненадежные зоны (White zones)</h3>
              <p className="text-3xl font-bold text-red-400">{summary.unreliable_buckets?.length || 0}</p>
            </div>
          </div>
        )
      )}

      {/* Вкладка: Рекомендации и Оверрайды */}
      {activeTab === 'recommendations' && (
        <div className="recommendations-list flex flex-col gap-4">
          {recs.length === 0 ? (
            <p className="text-gray-400">Нет активных рекомендаций. База в идеальном состоянии.</p>
          ) : (
            recs.map((rec, idx) => (
              <div key={idx} className="rec-item bg-gray-800 p-4 rounded border border-gray-700 flex justify-between items-center">
                <div>
                  <h4 className="text-red-400 font-bold">{rec.title || 'Аномалия калибровки'}</h4>
                  <p className="text-gray-300 text-sm">{rec.description}</p>
                  <p className="text-xs text-gray-500 mt-1">Bucket: {rec.bucket || 'N/A'}</p>
                </div>
                {rec.photo_id && rec.type === 'anomaly_followup' && (
                  <button
                    onClick={() => rec.photo_id && handleApplyOverride(rec.photo_id, rec.photo_id)}
                    className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors border border-gray-500"
                  >
                    Исследовать
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
