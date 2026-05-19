import React, { useState } from 'react';
import { useJobPolling } from '../hooks/useJobPolling';
import { useNotifications } from '../components/NotificationSystem';

export const SettingsPage: React.FC = () => {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [dataset, setDataset] = useState<'main' | 'calibration'>('main');
  const { jobState, error } = useJobPolling(activeJobId, {
    onComplete: (job) => {
      addNotification({ type: 'success', title: 'Job completed', message: job.message });
    },
    onError: (err) => {
      addNotification({ type: 'error', title: 'Job failed', message: err.message });
    }
  });
  const { addNotification } = useNotifications();

  const handleStartExtract = async () => {
    try {
      const res = await fetch('/api/jobs/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dataset, force: false, only_ids: [] })
      });
      if (!res.ok) throw new Error('Failed to start job');
      const { job_id } = await res.json();
      setActiveJobId(job_id);
      addNotification({ type: 'info', title: 'Job started', message: `Job ${job_id} started for ${dataset} dataset` });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to start extraction';
      addNotification({ type: 'error', title: 'Failed to start job', message: errorMessage });
    }
  };

  const handleCancelJob = async () => {
    if (!activeJobId) return;
    try {
      const res = await fetch(`/api/jobs/${activeJobId}/cancel`, { method: 'POST' });
      if (!res.ok) throw new Error('Failed to cancel job');
      addNotification({ type: 'info', title: 'Job cancelled', message: `Job ${activeJobId} cancelled` });
      setActiveJobId(null);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to cancel job';
      addNotification({ type: 'error', title: 'Failed to cancel job', message: errorMessage });
    }
  };

  return (
    <div className="settings-page p-6 max-w-4xl mx-auto">
      <h1 className="text-2xl font-bold mb-6 text-white">Управление пайплайном</h1>
      
      <div className="control-panel bg-gray-800 p-6 rounded-lg mb-6 border border-gray-700">
        <h2 className="text-xl mb-4 text-white">Пакетное извлечение признаков</h2>
        <select 
          className="bg-gray-900 text-white p-2 rounded mr-4 border border-gray-600"
          value={dataset} 
          onChange={(e) => setDataset(e.target.value as any)}
        >
          <option value="main">Main Dataset (1700+ фото)</option>
          <option value="calibration">Calibration Dataset</option>
        </select>
        
        <button
          onClick={handleStartExtract}
        disabled={jobState ? ['running', 'queued'].includes(jobState.status) : false}
          className="bg-blue-600 hover:bg-blue-500 text-white px-6 py-2 rounded disabled:opacity-50 mr-2"
        >
          Запустить сканирование
        </button>
        
        {jobState && ['running', 'queued'].includes(jobState.status) && (
          <button
            onClick={handleCancelJob}
            className="bg-red-600 hover:bg-red-500 text-white px-6 py-2 rounded"
          >
            Отменить
          </button>
        )}
        
        {jobState && ['failed', 'error'].includes(jobState.status) && (
          <button
            onClick={handleStartExtract}
            className="bg-yellow-600 hover:bg-yellow-500 text-white px-6 py-2 rounded"
          >
            Повторить
          </button>
        )}
      </div>

      {/* Индикатор прогресса */}
      {jobState && (
        <div className="job-status bg-gray-800 p-6 rounded-lg border border-gray-700">
          <div className="flex justify-between mb-2">
            <span className="text-gray-300">Статус: <b className={jobState.status === 'running' ? 'text-yellow-400' : jobState.status === 'completed' || jobState.status === 'done' ? 'text-green-400' : 'text-red-400'}>{jobState.status}</b></span>
            <span className="text-gray-300">
              {jobState.progress && typeof jobState.progress === 'object'
                ? `${((jobState.progress.completed / jobState.progress.total) * 100).toFixed(1)}%`
                : typeof jobState.progress === 'number'
                ? `${jobState.progress.toFixed(1)}%`
                : '0%'}
            </span>
          </div>
          <div className="w-full bg-gray-900 rounded-full h-4 mb-2">
            <div 
              className="bg-blue-500 h-4 rounded-full transition-all duration-500" 
              style={{ 
                width: jobState.progress && typeof jobState.progress === 'object'
                  ? `${(jobState.progress.completed / jobState.progress.total) * 100}%`
                  : typeof jobState.progress === 'number'
                  ? `${jobState.progress}%`
                  : '0%'
              }}
            ></div>
          </div>
          <div className="text-sm text-gray-400 font-mono">
            Log: {jobState.message || 'No message'}
          </div>
          {error && (
            <div className="text-sm text-red-400 mt-2">
              Error: {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
