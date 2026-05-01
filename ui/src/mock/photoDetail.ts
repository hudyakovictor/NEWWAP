export interface PhotoDetail {
  year: number;
  photo: string;
  reconstruction: any;
  zones: any[];
  pose: any;
  expression: any;
  texture: any;
  calibration: any;
  chronology: any;
  bayes: any;
  meta: any;
  notes: string[];
}

export const mockPhotoDetail: PhotoDetail = {
  year: 0,
  photo: "",
  reconstruction: {},
  zones: [],
  pose: {},
  expression: {},
  texture: {},
  calibration: {},
  chronology: {},
  bayes: {},
  meta: {},
  notes: []
};

export const FACE_ZONES: any[] = [
  { id: "forehead", name: "Forehead", group: "bone", priority: "max", weight: 1 },
  { id: "nasal_bridge", name: "Nasal Bridge", group: "bone", priority: "max", weight: 1 },
  { id: "orbital_l", name: "Left Orbital", group: "bone", priority: "high", weight: 1 },
  { id: "orbital_r", name: "Right Orbital", group: "bone", priority: "high", weight: 1 },
  { id: "cheek_l", name: "Left Cheek", group: "soft", priority: "medium", weight: 0.5 },
  { id: "cheek_r", name: "Right Cheek", group: "soft", priority: "medium", weight: 0.5 },
];

export function buildPhotoDetail(): any {
  return mockPhotoDetail;
}
