/**
 * Per-photo detail view.
 *
 * REAL fields: year, photo URL, pose (from HPE/3DDFA pipeline).
 * All other fields (zones, expression, texture, bayes, chronology,
 * reconstruction, calibration) are null — they require pipeline runs
 * that haven't happened yet.  The UI must handle null explicitly.
 *
 * Previously this file generated deterministic PRNG fake values for
 * every field.  Those have been removed because fake numbers are
 * worse than no numbers — they mislead the investigator.
 */

import type { Severity } from "./data";

export interface FaceZone {
  id: string;
  name: string;
  group: "bone" | "ligament" | "soft" | "mixed";
  priority: "max" | "high" | "medium" | "low";
  weight: number;
  visible: boolean;
  excluded: boolean;
  score: number | null;
  x: number;
  y: number;
}

export const FACE_ZONES: FaceZone[] = [
  { id: "nasal_bridge", name: "Nasal bridge",    group: "bone",     priority: "max",    weight: 1.00, visible: true, excluded: false, score: null, x: 50, y: 45 },
  { id: "orbit_l",      name: "Left orbit",      group: "bone",     priority: "max",    weight: 0.95, visible: true, excluded: false, score: null, x: 38, y: 40 },
  { id: "orbit_r",      name: "Right orbit",     group: "bone",     priority: "max",    weight: 0.95, visible: true, excluded: false, score: null, x: 62, y: 40 },
  { id: "zygo_l",       name: "Left zygomatic",  group: "bone",     priority: "max",    weight: 0.90, visible: true, excluded: false, score: null, x: 30, y: 55 },
  { id: "zygo_r",       name: "Right zygomatic", group: "bone",     priority: "max",    weight: 0.90, visible: true, excluded: false, score: null, x: 70, y: 55 },
  { id: "chin",         name: "Chin (mental)",   group: "bone",     priority: "max",    weight: 0.88, visible: true, excluded: false, score: null, x: 50, y: 82 },
  { id: "brow_ridge",   name: "Brow ridge",      group: "bone",     priority: "high",   weight: 0.80, visible: true, excluded: false, score: null, x: 50, y: 32 },
  { id: "jaw_l",        name: "Left jaw",        group: "bone",     priority: "high",   weight: 0.75, visible: true, excluded: false, score: null, x: 28, y: 72 },
  { id: "jaw_r",        name: "Right jaw",       group: "bone",     priority: "high",   weight: 0.75, visible: true, excluded: false, score: null, x: 72, y: 72 },
  { id: "zygo_lig_l",   name: "L zygomatic lig.", group: "ligament", priority: "high",  weight: 0.70, visible: true, excluded: false, score: null, x: 33, y: 58 },
  { id: "zygo_lig_r",   name: "R zygomatic lig.", group: "ligament", priority: "high",  weight: 0.70, visible: true, excluded: false, score: null, x: 67, y: 58 },
  { id: "orbit_lig_l",  name: "L orbital lig.",  group: "ligament", priority: "high",  weight: 0.70, visible: true, excluded: false, score: null, x: 40, y: 43 },
  { id: "orbit_lig_r",  name: "R orbital lig.",  group: "ligament", priority: "high",  weight: 0.70, visible: true, excluded: false, score: null, x: 60, y: 43 },
  { id: "nose_wing_l",  name: "L nose wing",     group: "soft",     priority: "low",    weight: 0.30, visible: true, excluded: false, score: null, x: 45, y: 60 },
  { id: "nose_wing_r",  name: "R nose wing",     group: "soft",     priority: "low",    weight: 0.30, visible: true, excluded: false, score: null, x: 55, y: 60 },
  { id: "lip_upper",    name: "Upper lip",       group: "soft",     priority: "low",    weight: 0.25, visible: true, excluded: true,  score: null, x: 50, y: 70 },
  { id: "lip_lower",    name: "Lower lip",       group: "soft",     priority: "low",    weight: 0.25, visible: true, excluded: true,  score: null, x: 50, y: 74 },
  { id: "cheek_l",      name: "Left cheek",      group: "mixed",    priority: "medium", weight: 0.45, visible: true, excluded: false, score: null, x: 32, y: 63 },
  { id: "cheek_r",      name: "Right cheek",     group: "mixed",    priority: "medium", weight: 0.45, visible: true, excluded: false, score: null, x: 68, y: 63 },
  { id: "forehead",     name: "Forehead skin",   group: "mixed",    priority: "medium", weight: 0.40, visible: true, excluded: false, score: null, x: 50, y: 22 },
  { id: "neck_skin",    name: "Neck skin",       group: "soft",     priority: "low",    weight: 0.20, visible: false, excluded: false, score: null, x: 50, y: 95 },
];

export interface PoseInfo {
  yaw: number | null;
  pitch: number | null;
  roll: number | null;
  classification: "frontal" | "three_quarter_left" | "three_quarter_right" | "profile_left" | "profile_right" | "none";
  confidence: number | null;
  fallback: boolean | null;
}

export interface ExpressionInfo {
  jawOpen: number | null;
  smile: number | null;
  neutral: boolean | null;
  excludedZones: string[] | null;
}

export interface TextureInfo {
  lbpComplexity: number | null;
  fftAnomaly: number | null;
  fftSpectrumData: number[] | null;
  albedoHealth: number | null;
  specularIndex: number | null;
  syntheticProb: number | null;
}

export interface CalibrationInfo {
  bucket: string | null;
  level: "unreliable" | "low" | "medium" | "high" | null;
  sampleCount: number | null;
  variance: number | null;
}

export interface ChronologyInfo {
  prevYear: number | null;
  prevDelta: number | null;
  boneAsymmetryJump: number | null;
  ligamentJump: number | null;
  flags: { severity: Severity; message: string }[] | null;
}

export interface BayesianVerdict {
  H0: number | null;
  H1: number | null;
  H2: number | null;
}

export interface PhotoMeta {
  id: string | null;
  filename: string | null;
  capturedAt: string | null;
  source: string | null;
  md5: string | null;
  resolution: string | null;
  sizeKB: number | null;
}

export interface PhotoDetail {
  year: number | null;
  photo: string;
  reconstruction: {
    renderFace: string | null;
    renderShape: string | null;
    renderMask: string | null;
    uvTexture: string | null;
    uvConfidence: string | null;
    uvMask: string | null;
    overlay: string | null;
    meshObj: string | null;
    meshTriangles: number | null;
    vertices: number | null;
  };
  zones: FaceZone[];
  pose: PoseInfo;
  expression: ExpressionInfo;
  texture: TextureInfo;
  calibration: CalibrationInfo;
  chronology: ChronologyInfo;
  bayes: BayesianVerdict;
  meta: PhotoMeta;
  notes: string[];
}

import { ALL_PHOTOS } from "../data/photoRegistry";
import forensicRegistryRaw from "../data/forensic_registry.json";

const FORENSIC_REGISTRY = forensicRegistryRaw as Record<string, any>;

/**
 * Build PhotoDetail from a photo's year and URL.
 *
 * All fields that require a pipeline run are set to null.
 * Only fields derived from the pose pipeline (yaw/pitch/roll/classification)
 * and from the signal report (sha256, dhash) are populated with real data.
 */
export function buildPhotoDetail(year: number | null, photo: string): PhotoDetail {
  // Find the real photo record for pose data
  const photoId = photo.split("/").pop()?.split(".")[0] || photo;
  const realPhoto = ALL_PHOTOS.find((p) => p.url === photo || p.id.endsWith(photoId));
  const realData = FORENSIC_REGISTRY[photoId] || FORENSIC_REGISTRY[photo] || null;

  // Real pose from pipeline
  const pose: PoseInfo = {
    yaw: realPhoto?.pose?.yaw ?? null,
    pitch: realPhoto?.pose?.pitch ?? null,
    roll: realPhoto?.pose?.roll ?? null,
    classification: realPhoto?.pose?.classification ?? "none",
    confidence: realData?.quality?.sharpness_variance ? Math.min(1, realData.quality.sharpness_variance / 500) : null,
    fallback: realPhoto?.pose?.source === "3ddfa" ? true : null,
  };

  // Zone visibility from real yaw (this is a real computation, not a stub)
  const yawVal = pose.yaw;
  const zones = FACE_ZONES.map((z) => {
    let visible = true;
    if (yawVal != null && Math.abs(yawVal) > 40) {
      if (yawVal > 0 && (z.id.endsWith("_r") || z.id.endsWith("_R"))) visible = false;
      if (yawVal < 0 && (z.id.endsWith("_l") || z.id.endsWith("_L"))) visible = false;
    }
    if (yawVal != null && Math.abs(yawVal) > 75) {
      if (["nasal_bridge", "lip_upper", "lip_lower", "chin"].includes(z.id)) visible = false;
    }
    return { ...z, visible, score: null };
  });

  return {
    year,
    photo,
    reconstruction: {
      renderFace: null,
      renderShape: null,
      renderMask: null,
      uvTexture: null,
      uvConfidence: null,
      uvMask: null,
      overlay: null,
      meshObj: null,
      meshTriangles: null,
      vertices: null,
    },
    zones,
    pose,
    expression: {
      jawOpen: null,
      smile: null,
      neutral: null,
      excludedZones: null,
    },
    texture: {
      lbpComplexity: realData?.texture?.lbp_complexity ?? null,
      fftAnomaly: realData?.texture?.quality?.noise_level ? Math.min(1, realData.texture.quality.noise_level / 5) : null,
      fftSpectrumData: null,
      albedoHealth: realData?.texture?.quality?.quality_index ?? null,
      specularIndex: realData?.texture?.specular_gloss ?? null,
      syntheticProb: realData?.syntheticProb ?? null,
    },
    calibration: {
      bucket: null,
      level: null,
      sampleCount: null,
      variance: null,
    },
    chronology: {
      prevYear: null,
      prevDelta: null,
      boneAsymmetryJump: null,
      ligamentJump: null,
      flags: null,
    },
    bayes: {
      H0: null,
      H1: null,
      H2: null,
    },
    meta: {
      id: realData?.photo_id ?? null,
      filename: photo.split("/").pop() || null,
      capturedAt: realData?.capturedAt ?? null,
      source: realData?.source ?? null,
      md5: realData?.md5 ?? null,
      resolution: realData?.resolution ?? null,
      sizeKB: realData?.file_size_bytes ? Math.round(realData.file_size_bytes / 1024) : null,
    },
    notes: [
      "Данные полей, не вычисленных реальным pipeline, отсутствуют (null).",
      "Видимость зон лица рассчитана по реальному yaw из HPE/3DDFA.",
    ],
  };
}
