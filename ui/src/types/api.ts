export interface PhotoMeta {
  photo_id: string;
  date?: string | null;
  date_str?: string | null;
  bucket: string;
  filename?: string;
  pose: { yaw?: number; pitch?: number; roll?: number };
  has_mesh?: boolean;
  thumbnail_url?: string | null;
  source_url?: string | null;
  artifacts?: Record<string, string>;
  record?: PhotoMeta;
}

export interface EvidenceResult {
  verdict: string;
  posteriors: {
    H0: number;
    H1: number;
    H2: number;
  };
  geometric: {
    snr: number;
    anomalies_flagged: number;
  };
  texture?: {
    syntheticProb: number;
    h1_subtype?: {
      primary: string;
      confidence: number;
    };
  };
  zone_deltas?: Record<string, number>;
}

export interface MeshData {
  vertices: number[][];
  triangles: number[][];
  uv_coords?: number[][];
}

export interface MatrixResult {
  photo_ids: string[];
  matrix: number[][];
}
