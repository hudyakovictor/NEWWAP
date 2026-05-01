"""
Incremental pipeline smoke test with detailed logging.

Tests each pipeline module independently on a single photo,
then the full extract_photo_bundle, then pairwise comparison.

Usage:
    python scripts/pipeline_smoke_test.py [--photo <path>] [--phase 1|2|3|all]

Phase 1: Unit-level smoke tests (QualityGate, TextureAnalyzer, PoseDetector, ReconstructionAdapter)
Phase 2: Full extract_photo_bundle on 1 photo
Phase 3: Pairwise comparison (calculate_bayesian_evidence)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_FILE = REPO_ROOT / "logs" / "smoke_test.log"
RESULTS_FILE = REPO_ROOT / "logs" / "smoke_test_results.json"

_all_logs: list[dict] = []


def log(stage: str, message: str, level: str = "info", data: Any = None):
    ts = datetime.now().isoformat()
    entry = {"ts": ts, "stage": stage, "level": level, "message": message}
    if data is not None:
        entry["data"] = data
    _all_logs.append(entry)
    prefix = {"info": "  ", "ok": "✅", "warn": "⚠️", "fail": "❌", "step": "▶️"}.get(level, "  ")
    line = f"[{ts[11:19]}] {prefix} [{stage}] {message}"
    if data and isinstance(data, dict) and len(str(data)) < 200:
        line += f"  {data}"
    print(line, flush=True)


def save_results():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(_all_logs, f, indent=2, ensure_ascii=False)
    # Summary
    fails = [e for e in _all_logs if e["level"] == "fail"]
    warns = [e for e in _all_logs if e["level"] == "warn"]
    oks = [e for e in _all_logs if e["level"] == "ok"]
    summary = {
        "total": len(_all_logs),
        "ok": len(oks),
        "warn": len(warns),
        "fail": len(fails),
        "failed_stages": [e["stage"] for e in fails],
    }
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n{'='*60}")
    print(f"Results: {len(oks)} ok, {len(warns)} warn, {len(fails)} fail")
    print(f"Log: {LOG_FILE}")
    print(f"Summary: {RESULTS_FILE}")
    if fails:
        print(f"FAILED stages: {[e['stage'] for e in fails]}")
        return 1
    return 0


def _check_not_none(stage: str, label: str, value: Any) -> bool:
    if value is None:
        log(stage, f"{label} is None", "fail")
        return False
    return True


def _check_not_nan(stage: str, label: str, value: Any) -> bool:
    if value is None:
        log(stage, f"{label} is None", "fail")
        return False
    if isinstance(value, float) and (__import__("math")).isnan(value):
        log(stage, f"{label} is NaN", "fail")
        return False
    return True


def _check_range(stage: str, label: str, value: float, lo: float, hi: float) -> bool:
    if not _check_not_nan(stage, label, value):
        return False
    if value < lo or value > hi:
        log(stage, f"{label}={value:.4f} outside [{lo}, {hi}]", "warn")
        return False
    return True


# ── Phase 1: Unit-level smoke tests ──────────────────────────────────────────

def phase1_quality_gate(photo_path: Path) -> dict | None:
    stage = "quality_gate"
    log(stage, f"Testing QualityGate on {photo_path.name}", "step")
    t0 = time.monotonic()

    try:
        from pipeline.quality_gate import QualityGate
        qg = QualityGate()
        result = qg.evaluate(photo_path)
        dt = time.monotonic() - t0
        log(stage, f"QualityGate completed in {dt:.2f}s", "info")

        # Verify structure
        required_keys = ["sharpness_variance", "noise_level", "is_rejected", "flags"]
        for k in required_keys:
            if k not in result:
                log(stage, f"Missing key: {k}", "fail")
                return None

        # Verify values
        sv = result["sharpness_variance"]
        nl = result["noise_level"]
        _check_not_nan(stage, "sharpness_variance", sv)
        _check_range(stage, "sharpness_variance", sv, 0, 50000)
        _check_not_nan(stage, "noise_level", nl)
        _check_range(stage, "noise_level", nl, 0, 100)
        _check_not_none(stage, "is_rejected", result["is_rejected"])

        log(stage, f"sharpness_variance={sv:.1f}, noise_level={nl:.2f}, is_rejected={result['is_rejected']}", "ok",
            {"sharpness_variance": sv, "noise_level": nl, "is_rejected": result["is_rejected"]})
        return result

    except Exception as e:
        log(stage, f"Exception: {e}", "fail")
        traceback.print_exc()
        return None


def phase1_texture_analyzer(photo_path: Path) -> dict | None:
    stage = "texture_analyzer"
    log(stage, f"Testing SkinTextureAnalyzer on {photo_path.name}", "step")
    t0 = time.monotonic()

    try:
        from pipeline.texture import SkinTextureAnalyzer
        ta = SkinTextureAnalyzer()
        result = ta.analyze_image(photo_path)
        dt = time.monotonic() - t0
        log(stage, f"SkinTextureAnalyzer completed in {dt:.2f}s", "info")

        if "error" in result:
            log(stage, f"Texture analyzer returned error: {result['error']}", "fail")
            return None

        # Verify structure
        required_keys = [
            "lbp_complexity", "lbp_uniformity", "specular_gloss",
            "silicone_probability", "reliability_weight", "pore_density",
            "wrinkle_forehead", "wrinkle_nasolabial", "global_smoothness",
        ]
        for k in required_keys:
            if k not in result:
                log(stage, f"Missing key: {k}", "fail")
                return None

        # Verify ranges
        sp = result["silicone_probability"]
        _check_range(stage, "silicone_probability", sp, 0, 1)
        _check_range(stage, "lbp_uniformity", result["lbp_uniformity"], 0, 1)
        _check_range(stage, "specular_gloss", result["specular_gloss"], 0, 1)
        _check_range(stage, "reliability_weight", result["reliability_weight"], 0, 1)

        log(stage, f"silicone_prob={sp:.3f}, lbp_complexity={result['lbp_complexity']:.2f}, reliability={result['reliability_weight']:.2f}", "ok",
            {"silicone_probability": sp, "reliability_weight": result["reliability_weight"]})
        return result

    except Exception as e:
        log(stage, f"Exception: {e}", "fail")
        traceback.print_exc()
        return None


def phase1_pose_detector(photo_path: Path) -> dict | None:
    stage = "pose_detector"
    log(stage, f"Testing PoseDetector on {photo_path.name}", "step")
    t0 = time.monotonic()

    try:
        from pipeline.detect_pose import PoseDetector
        pd = PoseDetector(device="cpu")
        result = pd.get_pose(photo_path)
        dt = time.monotonic() - t0
        log(stage, f"PoseDetector completed in {dt:.2f}s", "info")

        # Verify structure
        required_keys = ["yaw", "pitch", "roll", "bucket", "pose_source"]
        for k in required_keys:
            if k not in result:
                log(stage, f"Missing key: {k}", "fail")
                return None

        # Verify ranges
        _check_range(stage, "yaw", result["yaw"], -180, 180)
        _check_range(stage, "pitch", result["pitch"], -90, 90)
        _check_range(stage, "roll", result["roll"], -90, 90)

        bucket = result["bucket"]
        valid_buckets = {
            "frontal", "left_threequarter_light", "left_threequarter_mid",
            "left_threequarter_deep", "left_profile",
            "right_threequarter_light", "right_threequarter_mid",
            "right_threequarter_deep", "right_profile", "unclassified",
        }
        if bucket not in valid_buckets:
            log(stage, f"Unknown bucket: {bucket}", "warn")

        log(stage, f"yaw={result['yaw']:.1f}, pitch={result['pitch']:.1f}, roll={result['roll']:.1f}, bucket={bucket}, source={result['pose_source']}", "ok",
            {"yaw": result["yaw"], "bucket": bucket, "pose_source": result["pose_source"]})
        return result

    except Exception as e:
        log(stage, f"Exception: {e}", "fail")
        traceback.print_exc()
        return None


def phase1_reconstruction(photo_path: Path) -> dict | None:
    stage = "reconstruction"
    log(stage, f"Testing ReconstructionAdapter on {photo_path.name}", "step")
    t0 = time.monotonic()

    try:
        from pipeline.reconstruction import ReconstructionAdapter
        adapter = ReconstructionAdapter(device="cpu", detector_device="cpu")
        result = adapter.reconstruct(photo_path)
        dt = time.monotonic() - t0
        log(stage, f"ReconstructionAdapter completed in {dt:.2f}s", "info")

        # Verify structure
        n_verts = result.vertices_world.shape[0]
        n_tris = result.triangles.shape[0]
        n_visible = int(result.visible_idx_renderer.sum()) if result.visible_idx_renderer is not None else 0

        _check_range(stage, "vertex_count", float(n_verts), 1000, 100000)
        _check_range(stage, "triangle_count", float(n_tris), 1000, 200000)

        if n_visible < 100:
            log(stage, f"Very few visible vertices: {n_visible}", "warn")

        # Check angles
        angles = result.angles_deg
        _check_range(stage, "recon_yaw", float(angles[1]), -90, 90)
        _check_range(stage, "recon_pitch", float(angles[0]), -90, 90)
        _check_range(stage, "recon_roll", float(angles[2]), -90, 90)

        # Check for trust issue
        trust_issue = result.payload.get("trust_issue")
        if trust_issue:
            log(stage, f"Trust issue: {trust_issue}", "warn")

        log(stage, f"vertices={n_verts}, triangles={n_tris}, visible={n_visible}, angles=[{angles[0]:.1f}, {angles[1]:.1f}, {angles[2]:.1f}]", "ok",
            {"vertex_count": n_verts, "visible_count": n_visible})

        return {
            "vertex_count": n_verts,
            "triangle_count": n_tris,
            "visible_count": n_visible,
            "angles_deg": angles.tolist(),
            "trust_issue": trust_issue,
        }

    except Exception as e:
        log(stage, f"Exception: {e}", "fail")
        traceback.print_exc()
        return None


# ── Phase 2: Full extract_photo_bundle ───────────────────────────────────────

def phase2_extract_bundle(photo_path: Path) -> dict | None:
    stage = "extract_bundle"
    log(stage, f"Testing extract_photo_bundle on {photo_path.name}", "step")
    t0 = time.monotonic()

    try:
        from core.analysis import extract_photo_bundle
        from core.utils import stable_photo_id
        from core.config import SETTINGS

        photo_id = stable_photo_id("main", photo_path, SETTINGS.main_photos_dir)
        output_dir = SETTINGS.storage_root / "main" / photo_id / "smoke_test"

        result = extract_photo_bundle(
            source_path=photo_path,
            dataset="main",
            photo_id=photo_id,
            output_dir=output_dir,
        )
        dt = time.monotonic() - t0
        log(stage, f"extract_photo_bundle completed in {dt:.2f}s", "info")

        # ── Verify summary.json structure ──
        required_top_keys = [
            "photo_id", "dataset", "filename", "bucket", "angle",
            "pose", "reconstruction", "quality", "texture_forensics",
            "metrics", "artifacts", "status", "extracted_at",
            "methodology_version", "artifact_version",
        ]
        for k in required_top_keys:
            if k not in result:
                log(stage, f"Missing top-level key: {k}", "fail")

        # ── Verify metrics ──
        metrics = result.get("metrics", {})
        expected_metric_keys = [
            "cranial_face_index", "jaw_width_ratio",
            "canthal_tilt_L", "canthal_tilt_R",
            "orbit_depth_L_ratio", "orbit_depth_R_ratio",
            "nose_width_ratio", "nose_projection_ratio",
            "texture_silicone_prob", "reliability_weight",
        ]
        missing_metrics = [k for k in expected_metric_keys if k not in metrics]
        if missing_metrics:
            log(stage, f"Missing metrics: {missing_metrics}", "fail")
        else:
            log(stage, f"All {len(expected_metric_keys)} key metrics present", "ok")

        # Check for None/0 in critical bone metrics
        for bone_key in ["cranial_face_index", "jaw_width_ratio", "nose_projection_ratio"]:
            val = metrics.get(bone_key)
            if val is None or val == 0:
                log(stage, f"Bone metric {bone_key} is {val}", "warn")

        # ── Verify status ──
        status = result.get("status")
        if status not in ("ready", "needs_review"):
            log(stage, f"Unexpected status: {status}", "fail")
        else:
            log(stage, f"status={status}", "ok")

        # ── Verify artifacts on disk ──
        artifacts = result.get("artifacts", {})
        for art_name, art_file in artifacts.items():
            art_path = output_dir / art_file
            if not art_path.exists():
                log(stage, f"Artifact missing on disk: {art_name} -> {art_file}", "fail")
            else:
                size = art_path.stat().st_size
                if size == 0:
                    log(stage, f"Artifact is empty: {art_name}", "fail")

        # ── Verify face_crop exists ──
        face_crop = output_dir / "face_crop.jpg"
        face_crop_png = output_dir / "face_crop.png"
        if not face_crop.exists() and not face_crop_png.exists():
            log(stage, "No face_crop file (jpg or png)", "warn")

        # ── Verify reconstruction cache ──
        recon_cache = output_dir / "reconstruction_v1.pkl"
        if not recon_cache.exists():
            log(stage, "No reconstruction_v1.pkl cache", "warn")

        # ── Print key values ──
        log(stage, f"bucket={result.get('bucket')}, status={status}, metrics_count={len(metrics)}", "info", {
            "bucket": result.get("bucket"),
            "status": status,
            "metrics_count": len(metrics),
            "artifact_count": len(artifacts),
            "methodology_version": result.get("methodology_version"),
        })

        return result

    except Exception as e:
        log(stage, f"Exception: {e}", "fail")
        traceback.print_exc()
        return None


# ── Phase 3: Pairwise comparison ────────────────────────────────────────────

def phase3_pairwise(summary_a: dict, summary_b: dict) -> dict | None:
    stage = "bayesian_evidence"
    log(stage, f"Testing calculate_bayesian_evidence on {summary_a.get('photo_id')} vs {summary_b.get('photo_id')}", "step")
    t0 = time.monotonic()

    try:
        from core.analysis import calculate_bayesian_evidence
        result = calculate_bayesian_evidence(summary_a, summary_b)
        dt = time.monotonic() - t0
        log(stage, f"calculate_bayesian_evidence completed in {dt:.2f}s", "info")

        # Verify structure
        required_keys = [
            "aId", "bId", "verdict", "geometric", "texture", "chronology",
            "pose", "dataQuality", "likelihoods", "priors", "posteriors",
            "methodologyVersion", "computationLog",
        ]
        for k in required_keys:
            if k not in result:
                log(stage, f"Missing key: {k}", "fail")

        # Verify posteriors
        posteriors = result.get("posteriors", {})
        for h in ["H0", "H1", "H2"]:
            if h not in posteriors:
                log(stage, f"Missing posterior: {h}", "fail")
            else:
                _check_range(stage, f"posterior_{h}", posteriors[h], 0, 1)

        # Check posteriors sum ≈ 1
        psum = sum(posteriors.get(h, 0) for h in ["H0", "H1", "H2"])
        if abs(psum - 1.0) > 0.05:
            log(stage, f"Posteriors sum={psum:.3f} (expected ≈1.0)", "warn")

        # Check verdict
        verdict = result.get("verdict")
        valid_verdicts = {"H0", "H1", "H2", "INSUFFICIENT_DATA"}
        if verdict not in valid_verdicts:
            log(stage, f"Unexpected verdict: {verdict}", "fail")
        else:
            log(stage, f"verdict={verdict}", "ok")

        # Check for 0.5 defaults (should not exist after FIX-C4)
        texture = result.get("texture", {})
        for field in ["fft", "lbp", "albedo", "specular"]:
            val = texture.get(field)
            if val == 0.5:
                log(stage, f"texture.{field}=0.5 — possible unfixed default", "warn")

        # Check computation log
        comp_log = result.get("computationLog", [])
        if not comp_log:
            log(stage, "Empty computationLog", "warn")
        else:
            log(stage, f"computationLog has {len(comp_log)} entries", "ok")

        # Print summary
        log(stage, f"verdict={verdict}, H0={posteriors.get('H0',0):.3f}, H1={posteriors.get('H1',0):.3f}, H2={posteriors.get('H2',0):.3f}", "info", {
            "verdict": verdict,
            "posteriors": posteriors,
            "coverage_ratio": result.get("dataQuality", {}).get("coverageRatio"),
        })

        return result

    except Exception as e:
        log(stage, f"Exception: {e}", "fail")
        traceback.print_exc()
        return None


# ── Main ─────────────────────────────────────────────────────────────────────

def find_test_photo() -> Path | None:
    """Find a frontal photo for testing."""
    # Try the already-extracted photo first
    candidate = REPO_ROOT / "ui" / "public" / "photos_main" / "2020_04_07.jpg"
    if candidate.exists():
        return candidate
    # Try any 2020 photo
    import glob
    photos_dir = REPO_ROOT / "ui" / "public" / "photos_main"
    if not photos_dir.exists():
        return None
    for p in sorted(photos_dir.glob("2020_*.jpg")):
        return p
    # Any photo
    for p in sorted(photos_dir.glob("*.jpg")):
        return p
    return None


def find_second_test_photo() -> Path | None:
    """Find a second photo from a different year for pairwise testing."""
    photos_dir = REPO_ROOT / "ui" / "public" / "photos_main"
    if not photos_dir.exists():
        return None
    # Find a photo from a different year than the first
    for year in ["2010", "2015", "2005", "1999", "2024"]:
        for p in sorted(photos_dir.glob(f"{year}_*.jpg")):
            return p
    return None


def main():
    parser = argparse.ArgumentParser(description="Pipeline smoke test")
    parser.add_argument("--photo", type=str, help="Path to test photo")
    parser.add_argument("--photo2", type=str, help="Path to second test photo (for pairwise)")
    parser.add_argument("--phase", type=str, default="all", help="Phase to run: 1, 2, 3, or all")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"DEEPUTIN Pipeline Smoke Test")
    print(f"{'='*60}")

    # Resolve test photo
    if args.photo:
        photo_path = Path(args.photo)
        if not photo_path.exists():
            print(f"Photo not found: {photo_path}")
            return 1
    else:
        photo_path = find_test_photo()
        if photo_path is None:
            print("No test photo found!")
            return 1

    print(f"Test photo: {photo_path}")
    print(f"File size: {photo_path.stat().st_size / 1024:.0f} KB")
    print()

    run_phase1 = args.phase in ("1", "all")
    run_phase2 = args.phase in ("2", "all")
    run_phase3 = args.phase in ("3", "all")

    # ── Phase 1 ──
    quality_result = None
    texture_result = None
    pose_result = None
    recon_result = None

    if run_phase1:
        print(f"\n{'='*60}")
        print("PHASE 1: Unit-level smoke tests")
        print(f"{'='*60}\n")

        quality_result = phase1_quality_gate(photo_path)
        texture_result = phase1_texture_analyzer(photo_path)
        pose_result = phase1_pose_detector(photo_path)
        recon_result = phase1_reconstruction(photo_path)

        phase1_ok = all(r is not None for r in [quality_result, texture_result, pose_result, recon_result])
        if not phase1_ok:
            print("\n⚠️  Phase 1 had failures. Fix before proceeding to Phase 2.")
            return save_results()

    # ── Phase 2 ──
    bundle_result = None

    if run_phase2:
        print(f"\n{'='*60}")
        print("PHASE 2: Full extract_photo_bundle")
        print(f"{'='*60}\n")

        bundle_result = phase2_extract_bundle(photo_path)

        if bundle_result is None:
            print("\n⚠️  Phase 2 failed. Fix before proceeding to Phase 3.")
            return save_results()

    # ── Phase 3 ──
    if run_phase3:
        print(f"\n{'='*60}")
        print("PHASE 3: Pairwise comparison")
        print(f"{'='*60}\n")

        # Need two extracted photos — extract first if not done
        if bundle_result is None:
            log("bayesian_evidence", "First photo not yet extracted, extracting now", "step")
            bundle_result = phase2_extract_bundle(photo_path)
            if bundle_result is None:
                log("bayesian_evidence", "First photo extraction failed", "fail")
                return save_results()

        # Find second photo
        if args.photo2:
            photo2_path = Path(args.photo2)
        else:
            photo2_path = find_second_test_photo()

        if photo2_path is None or not photo2_path.exists():
            log("bayesian_evidence", "No second photo found for pairwise test", "warn")
            print("Skipping Phase 3: no second photo available")
            return save_results()

        print(f"Second photo: {photo2_path}")

        # Extract second photo
        log("bayesian_evidence", f"Extracting second photo for comparison", "step")
        bundle2 = phase2_extract_bundle(photo2_path)
        if bundle2 is None:
            log("bayesian_evidence", "Second photo extraction failed", "fail")
            return save_results()

        s1 = bundle_result
        s2 = bundle2

        phase3_pairwise(s1, s2)

    return save_results()


if __name__ == "__main__":
    sys.exit(main())
