/**
 * Real anomaly detectors driven by the head-pose data.
 *
 * Three rules:
 *  1. extreme_pose: |yaw| > 80° → info, the photo is near-profile and most
 *     bone-structure metrics will be pose-gated;
 *  2. fallback_used: pose source = "3ddfa" → info, the primary HPE detector
 *     missed and we relied on the fallback model;
 *  3. pose_drift: for main-folder photos with date metadata, if two
 *     consecutive (by date) photos in the same year are ≤ 30 days apart
 *     and |Δyaw| > 60°, flag both as "pose drift" warn — physiologically
 *     normal but worth surfacing for review.
 *
 * The output is `AnomalyRecord[]` so existing UI consumers don't need to
 * change.
 */

import { MAIN_PHOTOS, type RealPhoto } from "./photoRegistry";
import type { AnomalyRecord } from "../api/types";

interface SignalReportSlim {
  count: number;
  closestDhashPairs?: { a: string; b: string; distance: number }[];
  duplicates?: { sha256: string; files: string[] }[];
}

// Static JSON import works in both Vite and Node (tsx). The file is a copy
// of public/signal-report.json kept in src/data/ for compile-time access.
import signalReport from "./signal-report.json";
const SIGNALS = signalReport as SignalReportSlim;

function id(rp: RealPhoto): string {
  return rp.id;
}

export function detectPoseAnomalies(): AnomalyRecord[] {
  const out: AnomalyRecord[] = [];

  // Rules 1 + 2 — per-photo
  for (const p of MAIN_PHOTOS) {
    const yaw = p.pose.yaw;
    if (yaw != null && Math.abs(yaw) > 80) {
      out.push({
        id: `pose.extreme.${id(p)}`,
        year: p.year ?? 0,
        severity: "info",
        kind: "pose",
        photoId: id(p),
        title: `Near-profile pose (yaw=${yaw.toFixed(1)}°) — bone-structure metrics will be pose-gated`,
        detectedAt: p.date ?? "unknown",
        resolved: false,
      });
    }
    if (p.pose.source === "3ddfa") {
      out.push({
        id: `pose.fallback.${id(p)}`,
        year: p.year ?? 0,
        severity: "info",
        kind: "pose",
        photoId: id(p),
        title: "HPE failed; pose recovered via 3DDFA-V3 fallback",
        detectedAt: p.date ?? "unknown",
        resolved: false,
      });
    }
  }

  // Rule 0 — byte-identical files only. Earlier we also surfaced dHash
  // near-duplicates as anomalies, but visual verification showed that
  // dHash 8×8 catches pose/framing similarity rather than identity, so
  // those finds are not actual mis-dating evidence. We keep them in the
  // signal report (Real signals page) for review but no longer promote
  // them to anomalies. SHA-256 duplicates remain real and reliable.
  const yearOf = (file: string) => {
    const m = /^(\d{4})_/.exec(file);
    return m ? +m[1] : null;
  };
  void yearOf;
  for (const d of SIGNALS?.duplicates ?? []) {
    out.push({
      id: `signals.sha_dup.${d.sha256.slice(0, 8)}`,
      year: 0,
      severity: "warn",
      kind: "calibration",
      title: `Byte-identical files: ${d.files.join(" / ")}`,
      detectedAt: "from signal-report",
      resolved: false,
    });
  }

  // Rule 3 — chronological pose drift
  const dated = MAIN_PHOTOS.filter((p) => p.date && p.pose.yaw != null).sort((a, b) =>
    a.date! < b.date! ? -1 : 1
  );
  for (let i = 1; i < dated.length; i++) {
    const a = dated[i - 1];
    const b = dated[i];
    if (a.year !== b.year) continue;
    const dt = (Date.parse(b.date!) - Date.parse(a.date!)) / (24 * 3600 * 1000);
    if (dt > 30) continue;
    const dy = Math.abs((b.pose.yaw ?? 0) - (a.pose.yaw ?? 0));
    if (dy > 60) {
      out.push({
        id: `pose.drift.${id(a)}.${id(b)}`,
        year: a.year ?? 0,
        severity: "warn",
        kind: "chronology",
        photoId: id(b),
        title: `Pose drift Δyaw=${dy.toFixed(0)}° within ${Math.round(dt)}d (${a.file} → ${b.file})`,
        detectedAt: b.date!,
        resolved: false,
      });
    }
  }

  return out;
}
