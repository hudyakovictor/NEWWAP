import { useState, useEffect, useCallback } from 'react';
import type { JobState } from '../types/jobs';

interface UseJobPollingOptions {
  pollInterval?: number;
  onComplete?: (job: JobState) => void;
  onError?: (error: Error) => void;
}

/**
 * Hook for polling job status from the backend.
 * Automatically polls the job endpoint at the specified interval
 * until the job reaches a terminal state.
 * 
 * @param jobId - The ID of the job to poll, or null to disable polling
 * @param options - Configuration options for polling behavior
 * @returns Object containing job state, loading status, error, and refetch function
 */
export function useJobPolling(jobId: string | null, options: UseJobPollingOptions = {}) {
  const { pollInterval = 1000, onComplete, onError } = options;
  const [jobState, setJobState] = useState<JobState | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchJobState = useCallback(async () => {
    if (!jobId) return;
    
    try {
      setLoading(true);
      setError(null);
      const res = await fetch(`/api/jobs/${jobId}`);
      if (!res.ok) throw new Error('Job not found');
      const data: JobState = await res.json();
      setJobState(data);
      
      const isTerminal = ['completed', 'failed', 'done', 'error'].includes(data.status);
      if (isTerminal) {
        if (data.status === 'completed' || data.status === 'done') {
          onComplete?.(data);
        } else {
          onError?.(new Error(data.message || 'Job failed'));
        }
      }
      
      return data;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch job status';
      setError(errorMessage);
      onError?.(err instanceof Error ? err : new Error(errorMessage));
      return null;
    } finally {
      setLoading(false);
    }
  }, [jobId, onComplete, onError]);

  useEffect(() => {
    if (!jobId) return;

    fetchJobState();
    
    const interval = setInterval(() => {
      fetchJobState().then((data) => {
        if (data && ['completed', 'failed', 'done', 'error'].includes(data.status)) {
          clearInterval(interval);
        }
      });
    }, pollInterval);

    return () => clearInterval(interval);
  }, [jobId, pollInterval, fetchJobState]);

  return { jobState, loading, error, refetch: fetchJobState };
}
