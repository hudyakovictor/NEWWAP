export interface CalibrationSummary {
  total_calibration_photos: number;
  covered_buckets_percent: number;
  health_score: number;
  total_buckets?: number;
  covered_buckets?: number;
  unreliable_buckets?: string[];
  buckets?: Record<string, BucketDetail>;
}

export interface BucketDetail {
  confidence_level: 'high' | 'medium' | 'low';
  photo_count: number;
  reference_photo_id: string | null;
  photos: string[];
}

export interface Recommendation {
  title: string;
  description: string;
  bucket?: string;
  type: string;
  priority: 'critical' | 'high' | 'medium';
  benefit?: string;
  photo_id?: string;
}
