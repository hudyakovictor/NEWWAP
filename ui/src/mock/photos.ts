// All mock data removed - using real API only
// Minimal exports to prevent import errors

export interface PhotoRecord {
  photo_id: string;
  id: string;
  filename: string;
  folder: string;
  year: number;
  date_str: string;
  bucket: string;
  pose: any;
  syntheticProb: number;
  bayesH0: number | null;
  photo: string;
  cluster: string | null;
  flags: string[];
  identity: string | null;
  expression: string | null;
  source: string | null;
  md5: string | null;
  resolution: string | null;
  yaw: number | null;
  poseSource: string | null;
  date: string;
  [key: string]: any;
}

export const PHOTOS: PhotoRecord[] = [];
export const ALL_PHOTOS: PhotoRecord[] = [];
