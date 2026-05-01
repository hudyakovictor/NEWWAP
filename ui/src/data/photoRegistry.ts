export interface RealPhoto {
  id: string;
  photo_id: string;
  filename: string;
  date_str: string;
  parsed_year: number;
  bucket: string;
  pose: {
    yaw: number;
    pitch: number;
    roll: number;
    source: string;
    classification: string;
  } | null;
  [key: string]: any;
}

export const ALL_PHOTOS: RealPhoto[] = [];
export const MAIN_PHOTOS: RealPhoto[] = [];
export const MYFACE_PHOTOS: RealPhoto[] = [];

export function poseDistribution(photos: RealPhoto[]): Record<string, number> {
  const counts: Record<string, number> = {
    frontal: 0,
    three_quarter_left: 0,
    three_quarter_right: 0,
    profile_left: 0,
    profile_right: 0,
    none: 0,
  };
  for (const p of photos) {
    const bucket = p.pose?.classification || "none";
    if (bucket in counts) {
      counts[bucket]++;
    } else {
      counts.none++;
    }
  }
  return counts;
}

export function sourceDistribution(photos: RealPhoto[]): Record<string, number> {
  const counts: Record<string, number> = {
    hpe: 0,
    "3ddfa": 0,
    none: 0,
  };
  for (const p of photos) {
    const src = p.pose?.source || "none";
    if (src in counts) {
      counts[src]++;
    } else {
      counts.none++;
    }
  }
  return counts;
}
