// Mock detailed per-photo data: 21 zones, pose, expression, texture, synthetic, calibration, chronology
import type { Severity } from "./data";

export interface FaceZone {
  id: string;
  name: string;
  group: "bone" | "ligament" | "soft" | "mixed";
  priority: "max" | "high" | "medium" | "low";
  weight: number;        // 0..1 used by comparison algorithm
  visible: boolean;      // in current pose
  excluded: boolean;     // dynamically excluded by expression
  score: number;         // 0..1 similarity contribution
  /** rough pct position on face canvas */
  x: number;
  y: number;
}

export const FACE_ZONES: FaceZone[] = [
  { id: "nasal_bridge", name: "Nasal bridge",    group: "bone",     priority: "max",    weight: 1.00, visible: true, excluded: false, score: 0.91, x: 50, y: 45 },
  { id: "orbit_l",      name: "Left orbit",      group: "bone",     priority: "max",    weight: 0.95, visible: true, excluded: false, score: 0.88, x: 38, y: 40 },
  { id: "orbit_r",      name: "Right orbit",     group: "bone",     priority: "max",    weight: 0.95, visible: true, excluded: false, score: 0.86, x: 62, y: 40 },
  { id: "zygo_l",       name: "Left zygomatic",  group: "bone",     priority: "max",    weight: 0.90, visible: true, excluded: false, score: 0.82, x: 30, y: 55 },
  { id: "zygo_r",       name: "Right zygomatic", group: "bone",     priority: "max",    weight: 0.90, visible: true, excluded: false, score: 0.79, x: 70, y: 55 },
  { id: "chin",         name: "Chin (mental)",   group: "bone",     priority: "max",    weight: 0.88, visible: true, excluded: false, score: 0.90, x: 50, y: 82 },
  { id: "brow_ridge",   name: "Brow ridge",      group: "bone",     priority: "high",   weight: 0.80, visible: true, excluded: false, score: 0.77, x: 50, y: 32 },
  { id: "jaw_l",        name: "Left jaw",        group: "bone",     priority: "high",   weight: 0.75, visible: true, excluded: false, score: 0.72, x: 28, y: 72 },
  { id: "jaw_r",        name: "Right jaw",       group: "bone",     priority: "high",   weight: 0.75, visible: true, excluded: false, score: 0.68, x: 72, y: 72 },
  { id: "zygo_lig_l",   name: "L zygomatic lig.", group: "ligament", priority: "high",  weight: 0.70, visible: true, excluded: false, score: 0.74, x: 33, y: 58 },
  { id: "zygo_lig_r",   name: "R zygomatic lig.", group: "ligament", priority: "high",  weight: 0.70, visible: true, excluded: false, score: 0.71, x: 67, y: 58 },
  { id: "orbit_lig_l",  name: "L orbital lig.",  group: "ligament", priority: "high",   weight: 0.70, visible: true, excluded: false, score: 0.69, x: 40, y: 43 },
  { id: "orbit_lig_r",  name: "R orbital lig.",  group: "ligament", priority: "high",   weight: 0.70, visible: true, excluded: false, score: 0.67, x: 60, y: 43 },
  { id: "nose_wing_l",  name: "L nose wing",     group: "soft",     priority: "low",    weight: 0.30, visible: true, excluded: false, score: 0.55, x: 45, y: 60 },
  { id: "nose_wing_r",  name: "R nose wing",     group: "soft",     priority: "low",    weight: 0.30, visible: true, excluded: false, score: 0.52, x: 55, y: 60 },
  { id: "lip_upper",    name: "Upper lip",       group: "soft",     priority: "low",    weight: 0.25, visible: true, excluded: true,  score: 0.00, x: 50, y: 70 },
  { id: "lip_lower",    name: "Lower lip",       group: "soft",     priority: "low",    weight: 0.25, visible: true, excluded: true,  score: 0.00, x: 50, y: 74 },
  { id: "cheek_l",      name: "Left cheek",      group: "mixed",    priority: "medium", weight: 0.45, visible: true, excluded: false, score: 0.62, x: 32, y: 63 },
  { id: "cheek_r",      name: "Right cheek",     group: "mixed",    priority: "medium", weight: 0.45, visible: true, excluded: false, score: 0.60, x: 68, y: 63 },
  { id: "forehead",     name: "Forehead skin",   group: "mixed",    priority: "medium", weight: 0.40, visible: true, excluded: false, score: 0.65, x: 50, y: 22 },
  { id: "neck_skin",    name: "Neck skin",       group: "soft",     priority: "low",    weight: 0.20, visible: false, excluded: false, score: 0.00, x: 50, y: 95 },
];

export interface PoseInfo {
  yaw: number;
  pitch: number;
  roll: number;
  classification: "frontal" | "three_quarter_left" | "three_quarter_right" | "profile_left" | "profile_right";
  confidence: number;
  fallback: boolean;
}

export interface ExpressionInfo {
  jawOpen: number;          // 0..1
  smile: number;            // 0..1
  neutral: boolean;
  excludedZones: string[];  // zone ids
}

export interface TextureInfo {
  lbpComplexity: number;
  fftAnomaly: number;
  fftSpectrumData?: number[]; // [FIX-C1] Real FFT spectrum data from backend, 24 bins
  albedoHealth: number;     // skin viability 0..1
  specularIndex: number;    // higher = more synthetic-like
  syntheticProb: number;    // 0..1
}

export interface CalibrationInfo {
  bucket: string;           // e.g. "frontal_daylight"
  level: "unreliable" | "low" | "medium" | "high";
  sampleCount: number;
  variance: number;
}

export interface ChronologyInfo {
  prevYear?: number;
  prevDelta: number;        // years
  boneAsymmetryJump: number;
  ligamentJump: number;
  flags: { severity: Severity; message: string }[];
}

export interface BayesianVerdict {
  H0: number;
  H1: number;
  H2: number;
}

export interface PhotoMeta {
  id: string;
  filename: string;
  capturedAt: string;
  source: string;
  md5: string;
  resolution: string;
  sizeKB: number;
}

export interface PhotoDetail {
  year: number;
  photo: string;
  reconstruction: {
    renderFace: string;
    renderShape: string;
    renderMask: string;
    uvTexture: string;
    uvConfidence: string;
    uvMask: string;
    overlay: string;
    meshObj: string;
    meshTriangles: number;
    vertices: number;
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

function seeded(seed: number) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0xffffffff;
  };
}

import REGISTRY_RAW from "../data/forensic_registry.json";

const REGISTRY = REGISTRY_RAW as Record<string, any>;

export function buildPhotoDetail(year: number, photo: string): PhotoDetail {
  const photoId = photo.split("/").pop()?.split(".")[0] || photo;
  const realData = REGISTRY[photoId] || REGISTRY[photo] || null;

  const r = seeded(year * 31 + 7);
  const anomalyYear = year === 2012 || year === 2014 || year === 2023;
  const identityB = year >= 2015 && year <= 2020;

  const yaw = (r() - 0.5) * 20;
  const pitch = (r() - 0.5) * 10;
  const roll = (r() - 0.5) * 8;
  const poseClass: PoseInfo["classification"] =
    Math.abs(yaw) < 6 ? "frontal" : yaw > 0 ? "three_quarter_right" : "three_quarter_left";

  const jawOpen = r() * 0.25;
  const smile = year % 3 === 0 ? 0.45 + r() * 0.3 : r() * 0.2;
  const smiling = smile > 0.3;

  const zones = FACE_ZONES.map((z) => {
    // Visibility gating based on yaw (Pose-dependent forensics)
    let visible = true;
    const yawVal = realData?.reconstruction_summary?.pose?.[0] ?? yaw;
    if (Math.abs(yawVal) > 40) {
      if (yawVal > 0) {
        // Turning right (showing left profile) -> hide right-side zones
        if (z.id.endsWith("_r") || z.id.endsWith("_R")) visible = false;
      } else {
        // Turning left (showing right profile) -> hide left-side zones
        if (z.id.endsWith("_l") || z.id.endsWith("_L")) visible = false;
      }
    }
    if (Math.abs(yawVal) > 75) {
      // Extreme profile -> hide central zones too
      if (["nasal_bridge", "lip_upper", "lip_lower", "chin"].includes(z.id)) visible = false;
    }

    const excluded =
      z.excluded ||
      (smiling && ["lip_upper", "lip_lower", "nose_wing_l", "nose_wing_r", "cheek_l", "cheek_r"].includes(z.id));
    const baseScore =
      z.group === "bone" ? 0.75 + r() * 0.2 : z.group === "ligament" ? 0.6 + r() * 0.25 : 0.4 + r() * 0.3;
    const penalty = anomalyYear && (z.group === "bone" || z.group === "ligament") ? 0.25 : 0;
    const identityPenalty = identityB && z.group === "bone" ? 0.18 : 0;
    const zoneMatch = realData?.geometry?.zones?.find((rz: any) => rz.name === z.id);
    let finalScore = 0;
    if (zoneMatch) {
      finalScore = zoneMatch.status === "ok" ? (zoneMatch.bounded_score ?? 0) : 0;
    } else {
      finalScore = !visible || excluded ? 0 : Math.max(0, baseScore - penalty - identityPenalty);
    }
    return {
      ...z,
      visible,
      excluded,
      score: finalScore,
    };
  });

  const syntheticProb = anomalyYear ? 0.55 + r() * 0.3 : 0.1 + r() * 0.15;

  const H1 = identityB ? 0.55 + r() * 0.1 : anomalyYear ? 0.35 + r() * 0.15 : 0.06 + r() * 0.08;
  const H2 = 0.08 + r() * 0.1;
  const H0 = Math.max(0.05, 1 - H1 - H2);

  return {
    year,
    photo,
    reconstruction: {
      renderFace: `/storage/main/${photoId}/render_face.png`,
      renderShape: `/storage/main/${photoId}/render_shape.png`,
      renderMask: `/storage/main/${photoId}/render_mask.png`,
      uvTexture: `/storage/main/${photoId}/uv_texture.png`,
      uvConfidence: `/storage/main/${photoId}/uv_confidence.png`,
      uvMask: `/storage/main/${photoId}/uv_mask.png`,
      overlay: `/storage/main/${photoId}/face_overlay.png`,
      meshObj: `/storage/main/${photoId}/mesh.obj`,
      meshTriangles: 70_122,
      vertices: 35_709,
    },
    zones,
    pose: {
      yaw: realData?.reconstruction_summary?.pose?.[0] ?? +yaw.toFixed(1),
      pitch: realData?.reconstruction_summary?.pose?.[1] ?? +pitch.toFixed(1),
      roll: realData?.reconstruction_summary?.pose?.[2] ?? +roll.toFixed(1),
      classification: poseClass,
      confidence: realData?.quality?.sharpness_variance ? Math.min(1, realData.quality.sharpness_variance / 500) : +(0.72 + r() * 0.25).toFixed(2),
      fallback: r() < 0.1,
    },
    expression: {
      jawOpen: +jawOpen.toFixed(2),
      smile: +smile.toFixed(2),
      neutral: !smiling && jawOpen < 0.2,
      excludedZones: smiling
        ? ["lip_upper", "lip_lower", "nose_wing_l", "nose_wing_r", "cheek_l", "cheek_r"]
        : ["lip_upper", "lip_lower"],
    },
    texture: {
      lbpComplexity: realData?.texture?.lbp_complexity ?? +(anomalyYear ? 0.25 + r() * 0.15 : 0.65 + r() * 0.2).toFixed(2),
      fftAnomaly: realData?.texture?.quality?.noise_level ? Math.min(1, realData.texture.quality.noise_level / 5) : +(anomalyYear ? 0.55 + r() * 0.2 : 0.1 + r() * 0.15).toFixed(2),
      albedoHealth: realData?.texture?.quality?.quality_index ?? +(anomalyYear ? 0.35 + r() * 0.15 : 0.75 + r() * 0.15).toFixed(2),
      specularIndex: realData?.texture?.specular_gloss ?? +(anomalyYear ? 0.6 + r() * 0.2 : 0.15 + r() * 0.15).toFixed(2),
      syntheticProb: realData?.syntheticProb ?? +syntheticProb.toFixed(2),
    },
    calibration: {
      bucket:
        poseClass === "frontal" ? "frontal_daylight" : `${poseClass}_mixed_light`,
      level: anomalyYear ? "low" : year < 2005 ? "medium" : "high",
      sampleCount: 12 + Math.floor(r() * 40),
      variance: +(0.05 + r() * 0.08).toFixed(3),
    },
    chronology: {
      prevYear: year > 1999 ? year - 1 : undefined,
      prevDelta: 1,
      boneAsymmetryJump: +(anomalyYear ? 0.9 + r() * 0.4 : 0.1 + r() * 0.15).toFixed(2),
      ligamentJump: +(anomalyYear ? 0.75 + r() * 0.2 : 0.08 + r() * 0.1).toFixed(2),
      flags: [
        ...(anomalyYear
          ? [
              { severity: "danger" as Severity, message: "Bone asymmetry inversion between consecutive frontal frames" },
              { severity: "warn" as Severity, message: "Zygomatic ligament jump exceeds physiological threshold" },
            ]
          : []),
        ...(identityB
          ? [{ severity: "warn" as Severity, message: "Chronological cluster drift — belongs to cluster B" }]
          : []),
      ],
    },
    bayes: {
      H0: +H0.toFixed(2),
      H1: +H1.toFixed(2),
      H2: +H2.toFixed(2),
    },
    meta: {
      id: realData?.photo_id ?? `main-${year}-${Math.floor(r() * 0xffffff).toString(16).padStart(6, "0")}`,
      filename: photo.split("/").pop() || "photo.jpg",
      capturedAt: realData?.capturedAt ?? `${year}-${String(Math.floor(r() * 12) + 1).padStart(2, "0")}-${String(Math.floor(r() * 27) + 1).padStart(2, "0")}`,
      source: realData?.source ?? (year < 2005 ? "archival_scan" : year < 2015 ? "press_photo" : "digital"),
      md5: realData?.md5 ?? (Array.from({ length: 8 }, () => Math.floor(r() * 16).toString(16)).join("") + "2c92ad0b"),
      resolution: realData?.resolution ?? (year < 2005 ? "1024×768" : year < 2015 ? "1920×1280" : "3840×2560"),
      sizeKB: realData?.file_size_bytes ? Math.round(realData.file_size_bytes / 1024) : 180 + Math.floor(r() * 4800),
    },
    notes: [
      anomalyYear ? "Automatic flag raised — requires expert review." : "No automatic flags.",
      `Reconstruction cached with neutral expression = ${smiling ? "false" : "true"}.`,
      "Pose-dependent metrics computed only for visible zones.",
    ],
  };
}
