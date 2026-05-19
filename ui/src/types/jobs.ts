export interface JobState {
  job_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'done' | 'error';
  progress: {
    completed: number;
    total: number;
    percent?: number;
  } | number | null | undefined;
  message: string;
  errors: string[];
}
