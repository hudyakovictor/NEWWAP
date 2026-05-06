import os
import sys
import json
import shutil
import traceback
from pathlib import Path
from datetime import datetime
import numpy as np
from PIL import Image

sys.path.insert(0, "/Users/victorkhudyakov/dutin/core/3ddfa_v3")
sys.path.insert(0, "/Users/victorkhudyakov/dutin/newapp")
sys.path.insert(0, "/Users/victorkhudyakov/dutin/newapp/backend")

import re

def bucket_from_filename(name):
    m = re.search(r'y([-\d\.]+)', name)
    if not m:
        return "frontal"
    try:
        yaw = float(m.group(1))
    except Exception:
        return "frontal"
    yaw_abs = abs(yaw)
    if yaw_abs < 15.0:
        return "frontal"
    elif yaw_abs < 25.0:
        return "threequarter_light"
    elif yaw_abs < 45.0:
        return "threequarter_mid"
    elif yaw_abs < 70.0:
        return "threequarter_deep"
    else:
        return "profile"

def safe_save(img_obj, path, format="JPEG", **kwargs):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import time
    for attempt in range(3):
        try:
            img_obj.save(path, format, **kwargs)
            try:
                os.sync()
            except AttributeError:
                pass
            return
        except Exception as e:
            if attempt == 2:
                raise e
            time.sleep(0.5)

def safe_imwrite(path, img_np, params=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import cv2
    import time
    for attempt in range(3):
        try:
            if params is not None:
                cv2.imwrite(str(path), img_np, params)
            else:
                cv2.imwrite(str(path), img_np)
            try:
                os.sync()
            except AttributeError:
                pass
            return
        except Exception as e:
            if attempt == 2:
                raise e
            time.sleep(0.5)

def _compute_pair_calibration(photo_path, geo_metrics, texture_preds, pose_result, jaw_open_val, smile_val, pose_class, calib_df, excluded_flags=None):
    from backend.pipeline.calibration import find_calibration_match, _compute_linear_snr
    import pandas as pd
    import numpy as np
    from itertools import combinations

    calibrated_metrics = {}
    matched_photos = []
    
    if calib_df is None or len(calib_df) == 0:
        return {
            "mode": "pair_aware",
            "calib_photos_matched": 0,
            "matched_photos": [],
            "global_noise_baseline": 0.015,
            "pair_specific_noise_baseline": 0.015,
            "noise_reduction_pct": 0.0,
            "metrics": {}
        }
        
    try:
        # Нормализуем calib_df — нужна колонка "bucket" (а в CSV — "pose_bucket")
        _calib_for_match = calib_df.copy().rename(columns={"pose_bucket": "bucket"})

        target_quality = float(
            texture_preds.get("quality_quality_index")
            or texture_preds.get("quality_index")
            or (texture_preds.get("quality", {}) or {}).get("quality_index")
            or 0.7
        ) if texture_preds else 0.7

        top_k = find_calibration_match(
            calib_df=_calib_for_match,
            target_yaw=float(pose_result["yaw"]),
            target_pitch=float(pose_result["pitch"]),
            target_quality=target_quality,
            target_expr_mouth=float(jaw_open_val),
            target_expr_smile=float(smile_val),
            bucket=pose_class,
            k=5
        )
        
        # Build matched_photos metadata
        for idx, row in top_k.iterrows():
            # Calculate delta pose
            yaw_delta = abs(row.get("pose_yaw", 0.0) - float(pose_result["yaw"]))
            pitch_delta = abs(row.get("pose_pitch", 0.0) - float(pose_result["pitch"]))
            pose_delta = float(np.sqrt(yaw_delta**2 + pitch_delta**2))
            
            matched_photos.append({
                "filename": str(row.get("filename")),
                "pose_delta": round(pose_delta, 3),
                "quality_delta": round(abs(row.get("quality_overall", 0.7) - target_quality), 3),
                "match_rank": len(matched_photos) + 1
            })
            
        geo_prefix_cols = [c for c in calib_df.columns if c.startswith("geo_") and "3d" not in c]
        pair_noise = {}  # {metric_name: noise_baseline}

        top_k_records = [top_k.iloc[i] for i in range(len(top_k))]
        for col in geo_prefix_cols:
            metric = col[4:]  # strip "geo_"
            vals = []
            for ra, rb in combinations(top_k_records, 2):
                a, b = ra.get(col), rb.get(col)
                if pd.notna(a) and pd.notna(b):
                    vals.append(abs(float(a) - float(b)))
            if vals:
                pair_noise[metric] = float(np.mean(vals))

        tex_prefix_cols = [c for c in calib_df.columns if c.startswith("tex_")
                           and "quality" not in c and "notes" not in c and "3d" not in c]
        for col in tex_prefix_cols:
            metric = col[4:]
            vals = []
            for ra, rb in combinations(top_k_records, 2):
                a, b = ra.get(col), rb.get(col)
                if pd.notna(a) and pd.notna(b):
                    vals.append(abs(float(a) - float(b)))
            if vals:
                pair_noise[metric] = float(np.mean(vals))

        all_metrics = {}
        GEO_SKIP_KEYS = {"canthal_tilt_3d_L", "canthal_tilt_3d_R"}
        
        GEO_EXCLUSION_WHEN_JAW = {
            "gonial_angle_L", "gonial_angle_R", "mandibular_ramus_length",
            "jaw_width_ratio", "chin_projection_ratio", "gnathion_midline_deviation_ratio"
        }
        GEO_EXCLUSION_WHEN_SMILE = {"nasofacial_angle_ratio", "nose_width_ratio"}
        
        excl_keys = set()
        if excluded_flags:
            if excluded_flags.get("jaw_excluded"):
                excl_keys.update(GEO_EXCLUSION_WHEN_JAW)
            if excluded_flags.get("smile_excluded"):
                excl_keys.update(GEO_EXCLUSION_WHEN_SMILE)

        all_metrics.update({
            k: v for k, v in geo_metrics.items()
            if v is not None and k not in GEO_SKIP_KEYS and k not in excl_keys
        })
        if texture_preds:
            TEX_METRIC_KEYS = [
                "lbp_uniformity", "lbp_entropy", "glcm_contrast", "glcm_energy",
                "glcm_homogeneity", "glcm_correlation", "gabor_mean", "gabor_std",
                "laplacian_energy", "spot_density", "specular_gloss", "skin_tone_std",
                "pigmentation_index", "wrinkle_forehead", "nasolabial_depth",
                "crow_feet_score", "nose_pore_density", "uv_spot_density",
                "uv_wrinkle_energy", "uv_texture_entropy", "uv_silicone_flatness",
                "uv_retouch_score",
            ]
            tex_map = {k: texture_preds.get(k) for k in TEX_METRIC_KEYS}
            all_metrics.update({k: v for k, v in tex_map.items() if v is not None})

        bucket_calib = calib_df[calib_df["pose_bucket"] == pose_class]
        
        global_baselines = []
        pair_baselines = []

        for metric, value in all_metrics.items():
            col_geo = f"geo_{metric}"
            col_tex = f"tex_{metric}"
            col = col_geo if col_geo in calib_df.columns else (col_tex if col_tex in calib_df.columns else None)
            if col is None:
                continue
            
            global_vals = pd.to_numeric(bucket_calib[col], errors="coerce").dropna()
            if len(global_vals) < 3:
                continue
            
            global_mean = float(global_vals.mean())
            global_std = float(global_vals.std()) or 0.015
            z_score = abs(float(value) - global_mean) / (global_std + 1e-9)
            
            noise_bl = pair_noise.get(metric, global_std)
            snr = _compute_linear_snr(abs(float(value) - global_mean), noise_bl)
            
            global_baselines.append(global_std)
            pair_baselines.append(noise_bl)
            
            calibrated_metrics[metric] = {
                "value": round(float(value), 4),
                "global_mean": round(global_mean, 4),
                "global_std": round(global_std, 4),
                "z_score": round(z_score, 3),
                "noise_baseline": round(noise_bl, 4),
                "snr": round(snr, 3),
                "flagged": bool(z_score > 2.5),
                "metric_type": "geo" if col.startswith("geo_") else "tex",
            }
            
        g_baseline = float(np.mean(global_baselines)) if global_baselines else 0.015
        p_baseline = float(np.mean(pair_baselines)) if pair_baselines else 0.015
        reduction_pct = max(0.0, round(((g_baseline - p_baseline) / g_baseline) * 100.0, 1)) if g_baseline > 0 else 0.0
        
        return {
            "mode": "pair_aware",
            "calib_photos_matched": len(top_k),
            "matched_photos": matched_photos,
            "global_noise_baseline": round(g_baseline, 4),
            "pair_specific_noise_baseline": round(p_baseline, 4),
            "noise_reduction_pct": reduction_pct,
            "metrics": calibrated_metrics
        }
    except Exception as err:
        import traceback
        print(f"Error computing pair calibration for {photo_path.name}: {err}")
        traceback.print_exc()
        return {
            "mode": "pair_aware",
            "calib_photos_matched": 0,
            "matched_photos": [],
            "global_noise_baseline": 0.015,
            "pair_specific_noise_baseline": 0.015,
            "noise_reduction_pct": 0.0,
            "metrics": {}
        }

def extract_one(photo_path_str, out_root_dir_str, mode="calibration", calib_df=None, chrono_index=None):
    import time
    _t_start = time.time()
    photo_path = Path(photo_path_str)
    photo_name = photo_path.stem
    out_dir = Path(out_root_dir_str) / photo_name
    out_dir.mkdir(parents=True, exist_ok=True)
    
    result_path = out_dir / "result.json"
    if result_path.exists():
        try:
            with open(result_path, 'r') as f:
                existing = json.load(f)
                if existing.get("status") == "ready":
                    print(f"SKIP (already processed): {photo_path.name}")
                    return
        except Exception:
            pass

    errors = []
    print(f"Start processing: {photo_name}")
    
    try:
        img = Image.open(photo_path)
        img_info = {
            "width": img.width,
            "height": img.height,
            "format": img.format or "JPEG",
            "mode": img.mode,
        }
        
        # Create original and thumbnail directly in out_dir
        safe_save(img.convert("RGB"), out_dir / "original.jpg", "JPEG", quality=95)
        
        orig_w, orig_h = img.size
        new_h = 160
        new_w = int(orig_w * (new_h / orig_h))
        safe_save(img.copy().resize((new_w, new_h), Image.Resampling.LANCZOS), out_dir / "thumbnail.jpg", "JPEG", quality=85)
        
        # --- Quality evaluation using QualityGate ---
        from backend.pipeline.quality_gate import QualityGate
        gate = QualityGate()
        q_eval = gate.evaluate(photo_path)
        quality_metrics = {
            "success": True,
            "blur_value": q_eval["sharpness_variance"],
            "sharpness_value": q_eval["sharpness_variance"],
            "jpeg_blockiness": q_eval["noise_level"],
            "overall_quality": q_eval["overall_score"],
        }
        
        # --- 3D Reconstruction using ReconstructionAdapter ---
        from backend.pipeline.reconstruction import ReconstructionAdapter
        adapter = ReconstructionAdapter()
        res = adapter.reconstruct(photo_path)
        
        # --- Map 2D vertices back to the original full-size image ---
        v2d_img = res.vertices_image.copy()
        v2d_img[:, 1] = 224.0 - 1.0 - v2d_img[:, 1]
        trans_params = res.trans_params
        
        if trans_params is not None:
            w0, h0, s, t0, t1 = float(trans_params[0]), float(trans_params[1]), float(trans_params[2]), float(trans_params[3]), float(trans_params[4])
            target_size = 224.0
            w = w0 * s
            h = h0 * s
            left = w / 2.0 - target_size / 2.0 + (t0 - w0 / 2.0) * s
            up = h / 2.0 - target_size / 2.0 + (h0 / 2.0 - t1) * s
            
            v2d_mapped = v2d_img.copy()
            v2d_mapped[:, 0] = (v2d_mapped[:, 0] + left) / w * w0
            v2d_mapped[:, 1] = (v2d_mapped[:, 1] + up) / h * h0
        else:
            v2d_mapped = v2d_img
            
        yaw = float(res.angles_deg[1])
        ayaw = abs(yaw)
        if ayaw < 15.0:
            pose_class = "frontal"
        elif yaw < -70.0:
            pose_class = "left_profile"
        elif yaw > 70.0:
            pose_class = "right_profile"
        elif yaw < -45.0:
            pose_class = "left_threequarter_deep"
        elif yaw < -25.0:
            pose_class = "left_threequarter_mid"
        elif yaw < -10.0:
            pose_class = "left_threequarter_light"
        elif yaw > 45.0:
            pose_class = "right_threequarter_deep"
        elif yaw > 25.0:
            pose_class = "right_threequarter_mid"
        elif yaw > 10.0:
            pose_class = "right_threequarter_light"
        else:
            pose_class = "unclassified"
            
        pose_result = {
            "success": True,
            "yaw": float(res.angles_deg[1]),
            "pitch": float(res.angles_deg[0]),
            "roll": float(res.angles_deg[2]),
            "pose_source": "3ddfa",
            "pose_classification": pose_class
        }
        
        reconstruction = {
            "success": True,
            "vertices": res.vertices_world,
            "triangles": res.triangles,
            "uv_coords": res.uv_coords,
            "vertices_count": len(res.vertices_world),
            "triangles_count": len(res.triangles)
        }
        
        # Save vertices and mesh directly
        from backend.pipeline.alignment import canonicalize_vertices_for_bucket

        _raw_angles = np.array([
            pose_result.get("pitch", 0.0) or 0.0,
            pose_result.get("yaw", 0.0) or 0.0,
            pose_result.get("roll", 0.0) or 0.0,
        ])
        _vertices_canon = canonicalize_vertices_for_bucket(
            np.array(res.vertices_world), _raw_angles, pose_class
        )
        np.save(out_dir / "vertices.npy", _vertices_canon)          # канон для compare
        np.save(out_dir / "vertices_world_raw.npy", np.array(res.vertices_world))  # raw для дебага
        np.save(out_dir / "normals_world.npy", np.array(res.normals_world))       # normals для дебага/visibility
        np.save(out_dir / "normals_camera.npy", np.array(res.normals_camera))     # normals_camera для visibility
        np.save(out_dir / "vertices_camera.npy", np.array(res.vertices_camera))   # vertices_camera для z-buffer
        np.save(out_dir / "triangles.npy", np.array(res.triangles))               # triangles для ReconstructionResult
        with open(out_dir / "face_mesh.obj", 'w') as f:
             for v in res.vertices_world:
                 f.write(f"v {v[0]} {v[1]} {v[2]}\n")
             for t in res.triangles:
                 f.write(f"f {t[0]+1} {t[1]+1} {t[2]+1}\n")
        
        # --- Generate PERFECT UVs using uv_module with original image mapping ---
        import cv2
        from uv_module.hd_uv_generator import HDUVTextureGenerator, HDUVConfig
        
        from backend.pipeline.alignment import canonicalize_vertices_for_bucket
        
        # 1. Получаем бакет
        bucket_for_uv = pose_result.get("pose_classification", "frontal")

        # 2. Берем сырые углы [pitch, yaw, roll]
        raw_angles_for_uv = np.array([
            pose_result.get("pitch", 0.0) or 0.0,
            pose_result.get("yaw", 0.0) or 0.0,
            pose_result.get("roll", 0.0) or 0.0
        ])

        # 3. КАНОНИЗИРУЕМ ПРОСТРАНСТВО
        vertices_canon_for_uv = canonicalize_vertices_for_bucket(
            np.array(res.vertices_world), 
            raw_angles_for_uv, 
            bucket_for_uv
        )
        
        verts_3d = vertices_canon_for_uv.copy()
        verts_3d[:, 2] = -verts_3d[:, 2]  # Fix Z-buffer occlusion
        
        recon_dict_for_uv = {
            "vertices": vertices_canon_for_uv, # ИСПОЛЬЗУЕМ КАНОН!
            "triangles": res.triangles,
            "uv_coords": res.uv_coords,
            "vertices_2d": v2d_mapped,
            "vertices_3d": verts_3d
        }
        
        gen_cfg = HDUVConfig(uv_size=1024, super_sample=2, use_barycentric_bake=True)
        generator = HDUVTextureGenerator(gen_cfg)
        
        orig_img = cv2.imread(str(photo_path))
        orig_img_rgb = cv2.cvtColor(orig_img, cv2.COLOR_BGR2RGB)
        
        uv_tex_analysis, uv_tex_beauty, uv_mask_visible, uv_confidence, aux = generator.generate(
            image=orig_img_rgb, recon_dict=recon_dict_for_uv
        )
        
        uv_path = str(out_dir / "uv_texture_hd.jpg")
        safe_imwrite(uv_path, cv2.cvtColor(uv_tex_beauty, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        
        # --- Generate robust fallback mask using 3D normals ---
        uv_res = 1024
        uv_mask = np.zeros((uv_res, uv_res), dtype=np.uint8)
        uv_coords_img = np.zeros_like(res.uv_coords)
        uv_coords_img[:, 0] = res.uv_coords[:, 0] * (uv_res - 1)
        uv_coords_img[:, 1] = (1.0 - res.uv_coords[:, 1]) * (uv_res - 1)
        uv_coords_scaled = uv_coords_img.astype(np.int32)
        confidence_per_vertex = np.power(np.clip(res.normals_camera[:, 2], 0, 1), 4.0) * 255
        for tri in res.triangles:
            pts = uv_coords_scaled[tri]
            mean_conf = int(np.mean(confidence_per_vertex[tri]))
            if mean_conf > 0:
                cv2.fillConvexPoly(uv_mask, pts[:, :2], mean_conf)
        uv_confidence_mask = cv2.GaussianBlur(cv2.dilate(uv_mask, np.ones((3,3), np.uint8)), (5, 5), 0)
        
        # [FIX TX-03]: Сужение (эрод) маски уверенности.
        # Края маски содержат черные пиксели фона, которые алгоритм считал за "родинки".
        # Срезаем 3 пикселя с краев, чтобы анализировать только чистую кожу.
        kernel = np.ones((5, 5), np.uint8)
        uv_confidence_mask = cv2.erode(uv_confidence_mask, kernel, iterations=1)
        
        uv_mask_path = str(out_dir / "uv_confidence_mask.jpg")
        safe_imwrite(uv_mask_path, uv_confidence_mask, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        
        reconstruction["uv_texture_path"] = uv_path
        reconstruction["uv_confidence_mask_path"] = uv_mask_path
        
        # --- Generate refined skin-only segmentation mask EXACTLY like process_single_photo_v2.py ---
        seg_visible_224 = res.payload.get("raw_result", {}).get("seg_visible")
        h, w = img.height, img.width
        mask = np.zeros((h, w), dtype=np.uint8)
        
        if seg_visible_224 is not None and trans_params is not None:
            # 3DDFA_v3 Seg channels: [right_eye, left_eye, right_eyebrow, left_eyebrow, nose, up_lip, down_lip, skin]
            skin_224 = seg_visible_224[:, :, 7].copy()
            
            # Exclude eyes, eyebrows and lips
            for i in [0, 1, 2, 3, 5, 6]:
                part_mask = seg_visible_224[:, :, i]
                skin_224[part_mask > 0.5] = 0
                
            from util.io import back_resize_crop_img
            temp_mask_rgb = np.stack((skin_224, skin_224, skin_224), axis=-1).astype(np.uint8) * 255
            full_mask_rgb = back_resize_crop_img(temp_mask_rgb, trans_params, np.zeros((h, w, 3), dtype=np.uint8), resample_method=Image.NEAREST)
            mask = full_mask_rgb[:, :, 0]
        else:
            # Mesh fallback
            triangles = np.array(res.triangles)
            pts = v2d_mapped[:, :2].astype(np.int32)
            for tri in triangles:
                cv2.fillPoly(mask, [pts[tri]], 255)
                
        # --- Crop face using bounding box of the skin mask ---
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        coords = cv2.findNonZero(mask)
        if coords is not None:
            x, y, bw, bh = cv2.boundingRect(coords)
        else:
            x, y, bw, bh = 0, 0, 0, 0
            
        pad_x = int(bw * 0.15)
        pad_y = int(bh * 0.15)
        x1 = max(0, x - pad_x)
        y1 = max(0, y - pad_y)
        x2 = min(w, x + bw + pad_x)
        y2 = min(h, y + bh + pad_y)
        
        if coords is not None and bw > 0 and bh > 0 and x2 > x1 and y2 > y1:
            bbox_result = {
                "success": True,
                "x": float(x),
                "y": float(y),
                "w": float(bw),
                "h": float(bh),
                "score": 1.0,
                "kp5": []
            }
            
            face_crop_cv = img_cv[y1:y2, x1:x2]
            face_mask_cv = mask[y1:y2, x1:x2]
            masked_face_crop_cv = cv2.bitwise_and(face_crop_cv, face_crop_cv, mask=face_mask_cv)
            
            # Save as PNG with alpha transparency
            masked_face_crop_rgb = cv2.cvtColor(masked_face_crop_cv, cv2.COLOR_BGR2RGB)
            face_crop_rgba = np.zeros((face_crop_cv.shape[0], face_crop_cv.shape[1], 4), dtype=np.uint8)
            face_crop_rgba[:, :, :3] = masked_face_crop_rgb
            face_crop_rgba[:, :, 3] = face_mask_cv
            
            face_crop_pil = Image.fromarray(face_crop_rgba)
            safe_save(face_crop_pil, out_dir / "face_crop.png", "PNG")
            masked_face = masked_face_crop_rgb
        else:
            face_crop_pil = img.copy()
            safe_save(face_crop_pil, out_dir / "face_crop.png", "PNG")
            masked_face = np.array(img)
            bbox_result = {
                "success": True,
                "x": 0.0,
                "y": 0.0,
                "w": float(w),
                "h": float(h),
                "score": 1.0,
                "kp5": []
            }
        
        # --- Compute face stats ---
        # Compute only on non-zero pixels inside masked_face
        face_pixels = masked_face[np.any(masked_face > 0, axis=2)]
        if len(face_pixels) > 0:
            mean_lum = float(np.mean(face_pixels))
            std_lum = float(np.std(face_pixels))
            mean_r = float(np.mean(face_pixels[:, 0]))
            mean_g = float(np.mean(face_pixels[:, 1]))
            mean_b = float(np.mean(face_pixels[:, 2]))
            std_r = float(np.std(face_pixels[:, 0]))
            std_g = float(np.std(face_pixels[:, 1]))
            std_b = float(np.std(face_pixels[:, 2]))
            face_stats = {
                "success": True,
                "meanLum": mean_lum,
                "stdLum": std_lum,
                "meanR": mean_r,
                "meanG": mean_g,
                "meanB": mean_b,
                "stdR": std_r,
                "stdG": std_g,
                "stdB": std_b,
            }
        else:
            face_stats = {"success": False}
        
        # --- Skin texture analysis ---
        from backend.pipeline.texture import SkinTextureAnalyzer
        analyzer = SkinTextureAnalyzer()
        texture_preds = analyzer.analyze_image(
            face_crop_path=out_dir / "face_crop.png",
            uv_path=Path(uv_path),
            uv_mask_path=Path(uv_mask_path),
            yaw_deg=float(pose_result.get("yaw", 0.0)),
            pitch_deg=float(pose_result.get("pitch", 0.0)),
        )
        texture_actual = {}
        texture_notes = []
        
        # --- Geometric bone metrics extraction ---
        from backend.pipeline.scoring import extract_macro_bone_metrics
        from backend.pipeline.zones import MACRO_BONE_INDICES
        
        from backend.pipeline.alignment import canonicalize_vertices_for_bucket, _CANONICAL_YAW_BY_VIEW_GROUP

        # 1. Получаем бакет
        bucket = pose_result.get("pose_classification", "frontal")

        # 2. Берем сырые углы [pitch, yaw, roll]
        raw_angles = np.array([
            pose_result.get("pitch", 0.0) or 0.0,
            pose_result.get("yaw", 0.0) or 0.0,
            pose_result.get("roll", 0.0) or 0.0
        ])

        # 3. КАНОНИЗИРУЕМ ПРОСТРАНСТВО
        vertices_canon = canonicalize_vertices_for_bucket(
            np.array(res.vertices_world), 
            raw_angles, 
            bucket
        )

        # 4. Формируем "идеальные" углы, так как меш уже выровнен физически.
        # Теперь pitch и roll равны 0.0, а yaw равен идеальному таргету.
        target_angles = np.array([0.0, _CANONICAL_YAW_BY_VIEW_GROUP.get(bucket, 0.0), 0.0])

        # 5. Извлекаем метрики из ИДЕАЛЬНОЙ 3D-модели
        geo_metrics, reliability = extract_macro_bone_metrics(
            vertices_canon, 
            MACRO_BONE_INDICES, 
            target_angles
        )

        from backend.pipeline.zones import apply_expression_exclusion_mask

        excluded_flags = {}
        # 1. Получаем реальные параметры экспрессии из нейросети
        exp_params = res.payload.get("exp_params")
        if exp_params is not None and len(exp_params) >= 3:
            # 2. Проверяем мимику через исправленный модуль
            _, excluded_flags = apply_expression_exclusion_mask(
                base_mask=np.ones(len(vertices_canon), dtype=bool),
                exp_params=exp_params,
                bfm_indices=MACRO_BONE_INDICES
            )
            
            # 3. ЖЕСТКОЕ ИСКЛЮЧЕНИЕ: Открытый рот смещает всю нижнюю челюсть
            if excluded_flags.get("jaw_excluded"):
                compromised_jaw_metrics = [
                    'gonial_angle_L', 'gonial_angle_R', 
                    'mandibular_ramus_length', 
                    'jaw_width_ratio', 
                    'chin_projection_ratio',
                    'gnathion_midline_deviation_ratio' # Наша новая метрика из Итерации 1
                ]
                for metric_key in compromised_jaw_metrics:
                    if metric_key in geo_metrics:
                        geo_metrics[metric_key] = None # Ставим None, чтобы NoiseModel не сошел с ума
                        
            # 4. ЖЕСТКОЕ ИСКЛЮЧЕНИЕ: Улыбка смещает скулы, крылья носа и носогубные складки
            if excluded_flags.get("smile_excluded"):
                compromised_smile_metrics = [
                    'nasofacial_angle_ratio', 
                    'nose_width_ratio',
                ]
                for metric_key in compromised_smile_metrics:
                    if metric_key in geo_metrics:
                        geo_metrics[metric_key] = None

            # 5. Текстурные исключения при улыбке / открытом рте
            if excluded_flags.get("smile_excluded") and texture_preds:
                for tex_key in ['nasolabial_depth', 'crow_feet_score']:
                    if tex_key in texture_preds:
                        texture_preds[tex_key] = None

            if excluded_flags.get("jaw_excluded") and texture_preds:
                for tex_key in ['nasolabial_depth']:
                    if tex_key in texture_preds:
                        texture_preds[tex_key] = None

        geometric = geo_metrics
        
        parsed_year = None
        parsed_date_iso = None
        date_obj = None
        try:
            from backend.core.utils import parse_date_from_name
            date_iso, date_obj = parse_date_from_name(photo_path.name)
            parsed_date_iso = date_iso or None
            parsed_year = date_obj.year if date_obj else None
        except Exception:
            pass

        from core.utils import RAW_BUCKET_TO_UI
        bucket_ui = RAW_BUCKET_TO_UI.get(pose_class, "unknown")

        exp_params = res.payload.get("exp_params") if hasattr(res, "payload") and isinstance(res.payload, dict) else None
        jaw_open_val = 0.0
        smile_val = 0.0
        if exp_params is not None and len(exp_params) >= 3:
            jaw_open_val = float(abs(exp_params[0]))
            smile_val = float(max(abs(exp_params[1]), abs(exp_params[2])))

        GEO_SKIP_KEYS = {"canthal_tilt_3d_L", "canthal_tilt_3d_R"}
        TEX_METRIC_KEYS = [
            "lbp_uniformity", "lbp_entropy", "glcm_contrast", "glcm_energy",
            "glcm_homogeneity", "glcm_correlation", "gabor_mean", "gabor_std",
            "laplacian_energy", "spot_density", "specular_gloss", "skin_tone_std",
            "pigmentation_index", "wrinkle_forehead", "nasolabial_depth",
            "crow_feet_score", "nose_pore_density", "uv_spot_density",
            "uv_wrinkle_energy", "uv_texture_entropy", "uv_silicone_flatness",
            "uv_retouch_score",
        ]
        geo_count = len([k for k in geo_metrics if geo_metrics[k] is not None and k not in GEO_SKIP_KEYS])
        tex_count = len([k for k in texture_preds if texture_preds.get(k) is not None]) if texture_preds else 0
        expected_geo_len = len([k for k in geo_metrics if k not in GEO_SKIP_KEYS])
        expected = expected_geo_len + len(TEX_METRIC_KEYS)
        bucket_metrics_coverage = round((geo_count + tex_count) / max(expected, 1), 3)

        recon_a_landmarks_available = res.landmarks_106 is not None and len(res.landmarks_106) >= 48

        # --- Pair-Aware Calibration ---
        calibration_results = {}
        if mode == "main":
            calibration_results = _compute_pair_calibration(
                photo_path=photo_path,
                geo_metrics=geo_metrics,
                texture_preds=texture_preds,
                pose_result={"yaw": float(res.angles_deg[1]), "pitch": float(res.angles_deg[0])},
                jaw_open_val=jaw_open_val,
                smile_val=smile_val,
                pose_class=pose_class,
                calib_df=calib_df,
                excluded_flags=excluded_flags
            )
        else:
            calibration_results = {"mode": "calibration"}

        # --- Chronological Context ---
        abs_bucket = bucket_from_filename(photo_path.name)
        chrono_ctx = {
            "abs_bucket": abs_bucket,
            "bucket_position": None,
            "bucket_total": 0,
            "prev_photo": None,
            "prev_date": None,
            "days_since_prev": None,
            "next_photo": None,
            "next_date": None,
            "days_until_next": None,
        }
        
        lookup_bucket = abs_bucket if (chrono_index and abs_bucket in chrono_index) else pose_class
        if chrono_index and lookup_bucket in chrono_index:
            bucket_chrono = chrono_index[lookup_bucket]
            chrono_ctx["bucket_total"] = len(bucket_chrono)
            current_stem = photo_path.stem
            if current_stem in bucket_chrono:
                idx = bucket_chrono.index(current_stem)
                chrono_ctx["bucket_position"] = idx + 1
                if idx > 0:
                    prev_stem = bucket_chrono[idx - 1]
                    chrono_ctx["prev_photo"] = prev_stem
                    prev_iso, prev_obj = parse_date_from_name(prev_stem)
                    chrono_ctx["prev_date"] = prev_iso
                    if date_obj and prev_obj:
                        chrono_ctx["days_since_prev"] = int((date_obj - prev_obj).days)
                if idx < len(bucket_chrono) - 1:
                    next_stem = bucket_chrono[idx + 1]
                    chrono_ctx["next_photo"] = next_stem
                    next_iso, next_obj = parse_date_from_name(next_stem)
                    chrono_ctx["next_date"] = next_iso
                    if date_obj and next_obj:
                        chrono_ctx["days_until_next"] = int((next_obj - date_obj).days)

        # --- Excluded Zones ---
        geometry_excluded = []
        texture_excluded = []
        if excluded_flags.get("jaw_excluded"):
            geometry_excluded += ["gonial_angle_L", "gonial_angle_R", "mandibular_ramus_length", "jaw_width_ratio", "chin_projection_ratio", "gnathion_midline_deviation_ratio"]
            texture_excluded += ["nasolabial_depth"]
        if excluded_flags.get("smile_excluded"):
            geometry_excluded += ["nasofacial_angle_ratio", "nose_width_ratio"]
            texture_excluded += ["nasolabial_depth", "crow_feet_score"]

        result_dict = {
            "schema_version": "3.0",
            "analysis_type": "main_single" if mode == "main" else "calibration_single",
            "status": "ready",
            "pipeline": {
                "mode": mode,
                "timestamp": datetime.now().isoformat(),
                "processing_time_sec": round(time.time() - _t_start, 2),
                "reliability_weight": round(float(reliability), 3),
                "bucket_metrics_coverage": bucket_metrics_coverage,
            },
            "source": {
                "photo_path": str(photo_path),
                "filename": photo_path.name,
                "parsed_date": parsed_date_iso,
                "parsed_year": parsed_year,
                "image": {
                    "width": img_info["width"],
                    "height": img_info["height"],
                    "format": img_info["format"],
                    "mode": img_info["mode"],
                },
            },
            "pose": {
                "bucket": pose_class,
                "bucket_ui": bucket_ui,
                "yaw":   round(float(res.angles_deg[1]), 4),
                "pitch": round(float(res.angles_deg[0]), 4),
                "roll":  round(float(res.angles_deg[2]), 4),
            },
            "quality": {
                "overall":    quality_metrics.get("overall_quality"),
                "sharpness":  quality_metrics.get("sharpness_value"),
                "blur":       quality_metrics.get("blur_value"),
                "jpeg_noise": quality_metrics.get("jpeg_blockiness"),
            },
            "expression": {
                "mouth_open_intensity": round(jaw_open_val, 4),
                "smile_intensity":      round(smile_val, 4),
                "is_mouth_open":        jaw_open_val > 0.12,
                "is_smile":             smile_val > 0.08,
            },
            "face_detection": {
                "bbox": {
                    "x": bbox_result.get("x"),
                    "y": bbox_result.get("y"),
                    "w": bbox_result.get("w"),
                    "h": bbox_result.get("h"),
                    "score": bbox_result.get("score"),
                },
                "color": {
                    "mean_lum": face_stats.get("meanLum"),
                    "std_lum":  face_stats.get("stdLum"),
                    "mean_rgb": [face_stats.get("meanR"), face_stats.get("meanG"), face_stats.get("meanB")],
                    "std_rgb":  [face_stats.get("stdR"),  face_stats.get("stdG"),  face_stats.get("stdB")],
                } if face_stats.get("success") else None,
            },
            "reconstruction": {
                "success":        reconstruction.get("success", False),
                "vertices_count": reconstruction.get("vertices_count"),
                "triangles_count": reconstruction.get("triangles_count"),
                "ipd_available":  recon_a_landmarks_available,
            },
            "geometry": {
                "excluded_zones": geometry_excluded,
                **{k: v for k, v in geo_metrics.items()}
            },
            "texture": {
                "excluded_zones": texture_excluded,
                # Universal
                "lbp_uniformity":     texture_preds.get("lbp_uniformity") if texture_preds else None,
                "lbp_entropy":        texture_preds.get("lbp_entropy") if texture_preds else None,
                "glcm_contrast":      texture_preds.get("glcm_contrast") if texture_preds else None,
                "glcm_energy":        texture_preds.get("glcm_energy") if texture_preds else None,
                "glcm_homogeneity":   texture_preds.get("glcm_homogeneity") if texture_preds else None,
                "glcm_correlation":   texture_preds.get("glcm_correlation") if texture_preds else None,
                "gabor_mean":         texture_preds.get("gabor_mean") if texture_preds else None,
                "gabor_std":          texture_preds.get("gabor_std") if texture_preds else None,
                "laplacian_energy":   texture_preds.get("laplacian_energy") if texture_preds else None,
                "spot_density":       texture_preds.get("spot_density") if texture_preds else None,
                "specular_gloss":     texture_preds.get("specular_gloss") if texture_preds else None,
                "skin_tone_std":      texture_preds.get("skin_tone_std") if texture_preds else None,
                "pigmentation_index": texture_preds.get("pigmentation_index") if texture_preds else None,

                # Conditional (None если ракурс не тот)
                "wrinkle_forehead":   texture_preds.get("wrinkle_forehead") if texture_preds else None,
                "nasolabial_depth":   texture_preds.get("nasolabial_depth") if texture_preds else None,
                "crow_feet_score":    texture_preds.get("crow_feet_score") if texture_preds else None,
                "nose_pore_density":  texture_preds.get("nose_pore_density") if texture_preds else None,

                # UV zone
                "uv_spot_density":      texture_preds.get("uv_spot_density") if texture_preds else None,
                "uv_wrinkle_energy":    texture_preds.get("uv_wrinkle_energy") if texture_preds else None,
                "uv_texture_entropy":   texture_preds.get("uv_texture_entropy") if texture_preds else None,
                "uv_silicone_flatness": texture_preds.get("uv_silicone_flatness") if texture_preds else None,
                "uv_retouch_score":     texture_preds.get("uv_retouch_score") if texture_preds else None,

                # Quality
                "quality": {
                    "sharpness_score": texture_preds.get("quality_sharpness_score") if texture_preds else None,
                    "noise_score":     texture_preds.get("quality_noise_score") if texture_preds else None,
                    "quality_index":   (
                        texture_preds.get("quality_quality_index")
                        or texture_preds.get("quality_index")
                    ) if texture_preds else None,
                },
                "notes": texture_notes,
            },
            "calibration": calibration_results,
            "chronological_context": chrono_ctx,
            "files": {
                "_storage_dir":     str(out_dir),
                "original":         "original.jpg",
                "thumbnail":        "thumbnail.jpg",
                "face_crop":        "face_crop.png",
                "mesh_obj":         "face_mesh.obj",
                "vertices_canon":   "vertices.npy",
                "vertices_raw":     "vertices_world_raw.npy",
                "uv_texture":       "uv_texture_hd.jpg",
                "uv_mask":          "uv_confidence_mask.jpg",
            },
            "errors": errors,
        }

        def recursive_round(obj, precision=4):
            if isinstance(obj, (bool, np.bool_)):
                return bool(obj)
            elif isinstance(obj, (float, np.floating)):
                return round(float(obj), precision)
            elif isinstance(obj, (int, np.integer)):
                return int(obj)
            elif isinstance(obj, dict):
                return {k: recursive_round(v, precision) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [recursive_round(x, precision) for x in obj]
            return obj
        rounded_dict = recursive_round(result_dict)

        with open(out_dir / "result.json", 'w') as f:
            json.dump(rounded_dict, f, indent=2, default=str)
            
        print(f"Finished extracting ONE photo: {photo_name}")
        
    except Exception as e:
        print(f"Error processing {photo_name}: {e}")
        traceback.print_exc()
        error_result = {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__,
            "photo_path": str(photo_path),
            "timestamp": datetime.now().isoformat(),
            "artifact_version": "1.0",
        }
        try:
            with open(out_dir / "result.json", 'w') as f:
                json.dump(error_result, f, indent=4)
        except Exception as write_err:
            print(f"Failed to write error result: {write_err}")

def run_report_mode(test_photos, out_dir, calib_df):
    import json
    import numpy as np
    from pathlib import Path
    from collections import defaultdict
    from datetime import datetime

    print(f"[report mode] Starting report generation inside {out_dir}...")
    all_results = []
    
    # R3-1: Read all result.json from out_dir
    for p in test_photos:
        rj = Path(out_dir) / Path(p).stem / "result.json"
        if rj.exists():
            try:
                with open(rj, "r") as f:
                    data = json.load(f)
                if data.get("status") == "ready":
                    all_results.append(data)
            except Exception as e:
                print(f"Error reading result for {Path(p).stem}: {e}")
                
    if not all_results:
        print("⚠️ No valid processed photos found! Cannot build report.")
        return

    # Group by abs_bucket
    by_bucket = defaultdict(list)
    for r in all_results:
        abs_b = r.get("chronological_context", {}).get("abs_bucket", "frontal")
        by_bucket[abs_b].append(r)
        
    print(f"[report mode] Grouped {len(all_results)} photos into buckets: {list(by_bucket.keys())}")

    # R3-2 & R3-F: Load vertices, normals, triangles and build ReconstructionResult objects
    from backend.pipeline.types import ReconstructionResult
    
    def load_reconstruction(result_data) -> ReconstructionResult:
        files = result_data.get("files", {})
        storage_dir = Path(files["_storage_dir"])
        v_world_path = storage_dir / "vertices_world_raw.npy"
        if v_world_path.exists():
            v_world = np.load(v_world_path)
        else:
            v_world = np.zeros((22856, 3), dtype=np.float32)
            
        N = len(v_world)

        v_canon = np.load(storage_dir / "vertices.npy") \
            if (storage_dir / "vertices.npy").exists() \
            else np.zeros((N, 3), dtype=np.float32)

        normals_world = np.load(storage_dir / "normals_world.npy") \
            if (storage_dir / "normals_world.npy").exists() \
            else np.zeros((N, 3), dtype=np.float32)

        normals_camera = np.load(storage_dir / "normals_camera.npy") \
            if (storage_dir / "normals_camera.npy").exists() \
            else np.zeros((N, 3), dtype=np.float32)

        v_cam = np.load(storage_dir / "vertices_camera.npy") \
            if (storage_dir / "vertices_camera.npy").exists() \
            else v_world

        triangles = np.load(storage_dir / "triangles.npy") \
            if (storage_dir / "triangles.npy").exists() \
            else np.zeros((1, 3), dtype=np.int32)

        angles = np.array([
            result_data["pose"]["pitch"],
            result_data["pose"]["yaw"],
            result_data["pose"]["roll"],
        ], dtype=np.float64)
        
        return ReconstructionResult(
            image_path=Path(storage_dir / "original.jpg"),
            vertices_world=v_world,
            vertices_camera=v_cam,
            vertices_image=v_world[:, :2],  # stub
            triangles=triangles,
            point_buffer=np.zeros((N, 3), dtype=np.float32),
            annotation_groups=[],
            visible_idx_renderer=np.arange(N),
            normals_world=normals_world,
            normals_camera=normals_camera,
            rotation_matrix=np.eye(3, dtype=np.float64),
            translation=np.zeros(3, dtype=np.float64),
            angles_deg=angles,
            pose_bucket=result_data["pose"].get("bucket", "frontal"),
        )

    def translate_reasoning(reasoning_lines):
        translated = []
        for line in reasoning_lines:
            if line.startswith("Bayesian Posterior:"):
                parts = line.replace("Bayesian Posterior:", "").strip().split(",")
                same_val, swap_val, diff_val = "0.00", "0.00", "0.00"
                for p in parts:
                    if "Same=" in p: same_val = p.split("=")[1].strip()
                    elif "Swap/Mask=" in p: swap_val = p.split("=")[1].strip()
                    elif "Diff=" in p: diff_val = p.split("=")[1].strip()
                translated.append(f"Апостериорные вероятности Байеса: Совпадение={same_val}, Подмена/Маска={swap_val}, Различие={diff_val}")
            elif "Geometry evidence interpreted as calibrated" in line:
                import re
                m = re.search(r"SNR=([\d\.]+)", line)
                snr_val = m.group(1) if m else "0.00"
                translated.append(f"Геометрические доказательства интерпретированы как откалиброванные; вклад канала геометрии учтен полностью с SNR={snr_val}.")
            elif "Geometry evidence interpreted as fallback" in line:
                import re
                m = re.search(r"SNR=([\d\.]+)", line)
                snr_val = m.group(1) if m else "0.00"
                translated.append(f"Геометрические доказательства интерпретированы как резервные (fallback); вклад канала геометрии ослаблен с исходным SNR={snr_val}.")
            elif "Geometry evidence interpreted as unavailable" in line:
                import re
                m = re.search(r"SNR=([\d\.]+)", line)
                snr_val = m.group(1) if m else "0.00"
                translated.append(f"Геометрические доказательства недоступны; канал геометрии был отключен, исходный SNR={snr_val} сохранен для отслеживания.")
            elif "Significant geometric deviation detected" in line:
                import re
                m = re.search(r"SNR=([\d\.]+)", line)
                snr_val = m.group(1) if m else "0.00"
                translated.append(f"Обнаружено значительное геометрическое отклонение (SNR={snr_val}).")
            elif "Geometry remains within the expected natural-variation band" in line:
                import re
                m = re.search(r"SNR=([\d\.]+)", line)
                snr_val = m.group(1) if m else "0.00"
                translated.append(f"Геометрия остается в пределах ожидаемой естественной вариации (SNR={snr_val}).")
            elif "Texture analysis indicates synthetic materials" in line:
                import re
                m = re.search(r"P=([\d\.]+)", line)
                p_val = m.group(1) if m else "0.00"
                translated.append(f"Анализ текстуры указывает на наличие синтетических материалов (P={p_val}).")
            elif "Hard identity conclusions were downgraded" in line:
                translated.append("Категоричные выводы об идентичности были снижены, так как геометрия получена из резервного прокси, а не из калиброванной модели.")
            elif "Hard identity conclusions were disabled" in line:
                translated.append("Категоричные выводы об идентичности заблокированы, так как не удалось установить рабочий канал геометрии.")
            elif "Confidence was capped at" in line:
                import re
                m = re.search(r"capped at ([\d\.]+)", line)
                cap_val = m.group(1) if m else "0.50"
                translated.append(f"Уровень уверенности ограничен на уровне {cap_val} политикой геометрических данных.")
            else:
                translated.append(line)
        return translated

    # R3-3 & R3-4: Compare chronologically and synthesize Bayesian verdicts
    from backend.pipeline.compare import PairComparisonEngine, _compute_linear_snr
    from backend.pipeline.calibration import CalibrationAnalyzer
    from backend.pipeline.verdict import BayesianMultiHypothesisEngine, GeometryEvidenceMode

    calib_analyzer = CalibrationAnalyzer()
    pair_engine = PairComparisonEngine(calibration=calib_analyzer)
    verdict_engine = BayesianMultiHypothesisEngine()

    timeline_by_bucket = {}

    for bucket, photos in by_bucket.items():
        # Sort photos in bucket chronologically by date
        sorted_photos = sorted(
            photos, 
            key=lambda x: x.get("source", {}).get("parsed_date") or "1900-01-01"
        )
        
        pairs = []
        for i in range(len(sorted_photos) - 1):
            pa = sorted_photos[i]
            pb = sorted_photos[i+1]
            
            ra = load_reconstruction(pa)
            rb = load_reconstruction(pb)
            
            try:
                cmp_result = pair_engine.compare(ra, rb)
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Error comparing {pa['source']['filename']} with {pb['source']['filename']}: {e}")
                continue
                
            # R3-A: Compute linear SNR
            noise_baseline = 0.015
            geometry_snr = _compute_linear_snr(
                signal_error=cmp_result.score_raw or 0.0,
                noise_baseline=noise_baseline
            )
            
            # Bayesian Synthesis
            chrono_flags = pb.get("chronological_context", {}).get("flags", [])
            texture_silicone = pb.get("texture", {}).get("uv_silicone_flatness", 0.0) or 0.0
            
            verdict = verdict_engine.synthesize(
                geometry_snr=geometry_snr,
                texture_silicone_prob=float(texture_silicone),
                chronology_flags=chrono_flags,
                geometry_evidence_mode=GeometryEvidenceMode.CALIBRATED,
            )
            
            # R3-B: Format comparison zones correctly
            zone_details_out = []
            for z in cmp_result.zones:
                zone_details_out.append({
                    "zone": z.name,
                    "raw_error": round(float(z.raw_error or 0), 4),
                    "bounded_score": round(float(z.bounded_score or 0), 4),
                    "delta_mm": round(float(z.delta_mm or 0), 3),
                    "bone_priority": z.bone_priority_class,
                    "status": z.status,
                })
            
            # Build delta days
            da = datetime.fromisoformat(pa["source"]["parsed_date"]) if pa["source"].get("parsed_date") else None
            db = datetime.fromisoformat(pb["source"]["parsed_date"]) if pb["source"].get("parsed_date") else None
            delta_days = int((db - da).days) if da and db else 0
            
            # БЛОКЕР 2 & БЛОКЕР 3 & ПРАВКА 7
            verdict_dict = verdict.to_dict()
            probs_raw = verdict.probabilities
            if hasattr(probs_raw, "items"):  # dict
                h0 = probs_raw.get("H0_same") if "H0_same" in probs_raw else probs_raw.get("H0", 0.0)
                h1 = probs_raw.get("H1_swap") if "H1_swap" in probs_raw else probs_raw.get("H1", 0.0)
                h2 = probs_raw.get("H2_diff") if "H2_diff" in probs_raw else probs_raw.get("H2", 0.0)
            else:
                h0 = getattr(probs_raw, "H0_same") if hasattr(probs_raw, "H0_same") else getattr(probs_raw, "H0", 0.0)
                h1 = getattr(probs_raw, "H1_swap") if hasattr(probs_raw, "H1_swap") else getattr(probs_raw, "H1", 0.0)
                h2 = getattr(probs_raw, "H2_diff") if hasattr(probs_raw, "H2_diff") else getattr(probs_raw, "H2", 0.0)

            print(f"DEBUG verdict.probabilities = {probs_raw}")

            pairs.append({
                "photo_a": pa["source"]["filename"],
                "photo_b": pb["source"]["filename"],
                "delta_days": delta_days,
                "comparison": {
                    "snr": round(geometry_snr, 3),
                    "zone_details": zone_details_out,
                    "score_raw": round(float(cmp_result.score_raw or 0), 4),
                    "robust_score_raw": round(float(cmp_result.robust_score_raw or 0), 4),
                    "provisional_band": cmp_result.provisional_band,
                    "robust_provisional_band": cmp_result.robust_provisional_band,
                    "geometry_evidence_mode": verdict_dict.get("evidence_snr", {}).get("geometry_evidence_mode"),
                },
                "verdict": {
                    "status":      verdict_dict["status"],       # "uncertain"
                    "fuzzy_label": verdict_dict["fuzzy_label"],  # "suspicious_texture"
                    "probabilities": {
                        "H0": round(float(h0), 4),
                        "H1": round(float(h1), 4),
                        "H2": round(float(h2), 4),
                    },
                    "confidence": round(float(verdict.confidence), 3),
                    "flags": verdict.flags,
                    "reasoning": translate_reasoning(verdict.reasoning),
                    "evidence_snr": verdict_dict.get("evidence_snr"),
                }
            })

        # R3-D: Inline timeline evaluation
        timeline_input = []
        for r in sorted_photos:
            p_date = r["source"]["parsed_date"] or "1900-01-01"
            timeline_input.append({
                "date": p_date,
                "recon": load_reconstruction(r),
                "photo_id": r["source"]["filename"]
            })
            
        timeline_flags = []
        SNR_IMPOSSIBLE = 3.0
        SNR_TRANSITION = 2.5
        BASELINE_MATCH = 1.5
        baseline_recon = timeline_input[0]["recon"] if timeline_input else None
        for i in range(1, len(timeline_input)):
            prev = timeline_input[i-1]
            curr = timeline_input[i]
            try:
                res_prev = pair_engine.compare(prev["recon"], curr["recon"])
                snr_prev = _compute_linear_snr(res_prev.score_raw or 0, 0.015)
                if snr_prev > SNR_IMPOSSIBLE:
                    timeline_flags.append({
                        "type": "IMPOSSIBLE_TRANSITION",
                        "date": curr["date"],
                        "snr": round(snr_prev, 3)
                    })
                if baseline_recon and snr_prev > SNR_TRANSITION:
                    res_base = pair_engine.compare(baseline_recon, curr["recon"])
                    snr_base = _compute_linear_snr(res_base.score_raw or 0, 0.015)
                    if snr_base < BASELINE_MATCH:
                        timeline_flags.append({
                            "type": "RETURN_TO_REFERENCE",
                            "date": curr["date"]
                        })
            except Exception as te:
                print(f"Error evaluating timeline step: {te}")

        # R3-E: Longitudinal trends and anomalies using build_longitudinal_model
        from backend.core.longitudinal import build_longitudinal_model
        
        summaries = []
        for r in sorted_photos:
            geo = r.get("geometry", {}) or {}
            tex = r.get("texture", {}) or {}
            summaries.append({
                "photo_id": r["source"]["filename"],
                "parsed_date": r["source"]["parsed_date"] or "1900-01-01",
                "metrics": {
                    k: v for k, v in {**geo, **tex}.items()
                    if isinstance(v, (int, float)) and v is not None
                },
                "quality_score": r["quality"].get("overall") or 0.0,
                "pose_reliability": r["pipeline"].get("reliability_weight") or 0.0,
                "bucket": r["pose"].get("bucket", "frontal"),
            })

        try:
            analyzer = build_longitudinal_model(summaries)
            analyzer.analyze_trends()
            analyzer.detect_anomalies()
            summary = analyzer.get_summary()

            # Сериализация трендов — analyzer.trends это dict[str, TrendAnalysis]
            trends_serialized = {}
            for metric_key, trend in (getattr(analyzer, "trends", {}) or {}).items():
                trends_serialized[metric_key] = {
                    "slope": round(float(getattr(trend, "slope", 0)), 4),
                    "r_squared": round(float(getattr(trend, "r_squared", 0)), 4),
                    "direction": getattr(trend, "direction", "stable"),
                    "is_significant": getattr(trend, "is_significant", False),
                }

            # Сериализация аномалий
            anomalies_serialized = []
            for a in (getattr(analyzer, "anomalies", []) or []):
                anomalies_serialized.append({
                    "photo_id": getattr(a, "photo_id", ""),
                    "metric_key": getattr(a, "metric_key", ""),
                    "severity": getattr(a, "severity", "info"),
                    "deviation_sigma": round(float(getattr(a, "deviation_sigma", 0)), 2),
                    "explanation": getattr(a, "explanation", ""),
                    "is_critical": getattr(a, "severity", "") == "danger",
                })

            longitudinal_data = {
                "trends_analyzed": summary.get("trends_analyzed", 0),
                "trends": trends_serialized,
                "anomalies_detected": summary.get("anomalies_detected", 0),
                "anomalies": anomalies_serialized,
                "aging_consistency_score": round(float(summary.get("aging_consistency_score", 1.0)), 3),
            }
        except Exception as e:
            print(f"Error in longitudinal analysis for {bucket}: {e}")
            longitudinal_data = {"trends": {}, "anomalies": [], "aging_consistency_score": 1.0}

        timeline_by_bucket[bucket] = {
            "pairs": pairs,
            "timeline_flags": timeline_flags,
            "longitudinal": longitudinal_data
        }

    # R3-7: Build Global Verdict & Global Stats
    total_photos = len(all_results)
    photos_by_bucket = {b: len(lst) for b, lst in by_bucket.items()}
    
    all_dates = [
        r["source"]["parsed_date"]
        for r in all_results
        if r.get("source", {}).get("parsed_date") 
        and r["source"]["parsed_date"] > "1900-01-01"
    ]
    date_range = {
        "from": min(all_dates) if all_dates else None,
        "to": max(all_dates) if all_dates else None
    }
    
    all_qualities = [r["quality"]["overall"] for r in all_results if r.get("quality", {}).get("overall") is not None]
    quality_stats = {
        "mean": round(float(np.mean(all_qualities)), 3) if all_qualities else 0.7,
        "min": round(float(np.min(all_qualities)), 3) if all_qualities else 0.7
    }

    # Generate synthesis of global status
    global_status = "same_person"
    critical_flags = []
    suspicious_windows = []
    
    for bucket, b_data in timeline_by_bucket.items():
        for p in b_data["pairs"]:
            if p["verdict"]["status"] in ["different_person", "double_stand_in"]:
                global_status = "unresolved_anomalies"
            for fl in p["verdict"]["flags"]:
                critical_flags.append(f"[{bucket}] Pair {p['photo_a']} -> {p['photo_b']}: {fl}")
                
        for anom in b_data["longitudinal"].get("anomalies", []):
            if anom.get("is_critical"):
                global_status = "unresolved_anomalies"
                suspicious_windows.append(f"[{bucket}] Metric '{anom['metric']}' anomaly on {anom['photo_id']}: severity {anom['severity']}")

    all_h0 = []
    all_reliability = []
    for b_data in timeline_by_bucket.values():
        for pair in b_data["pairs"]:
            h0 = pair["verdict"]["probabilities"].get("H0", 0.0)
            # взять reliability из result.json фото_a
            rel = next((r["pipeline"]["reliability_weight"] for r in all_results
                        if r["source"]["filename"] == pair["photo_a"]), 0.5)
            all_h0.append(h0)
            all_reliability.append(rel)

    if all_h0 and sum(all_reliability) > 0:
        w = np.array(all_reliability)
        confidence = float(np.average(all_h0, weights=w))
    else:
        confidence = 0.95 if global_status == "same_person" else 0.45

    report_json = {
        "schema_version": "3.0",
        "analysis_type": "full_report",
        "generated_at": datetime.now().isoformat(),
        "dataset": {
            "total_photos": total_photos,
            "photos_by_bucket": photos_by_bucket,
            "date_range": date_range,
            "quality_stats": quality_stats
        },
        "timeline_by_bucket": timeline_by_bucket,
        "global_verdict": {
            "status": global_status,
            "confidence": round(confidence, 3),
            "critical_flags": list(set(critical_flags)),
            "suspicious_windows": list(set(suspicious_windows)),
            "summary": (
                "Критических анатомических аномалий не обнаружено. "
                "Незначительные отклонения соответствуют естественному старению и вариациям освещения."
                if global_status == "same_person" else
                "Обнаружены критические анатомические аномалии. "
                "Одно или несколько хронологических сравнений указывает на потенциальное несоответствие идентичности."
            )
        }
    }

    # Save to out_dir / report.json
    report_path = Path(out_dir) / "report.json"
    with open(report_path, "w") as f:
        json.dump(report_json, f, indent=2, default=str)
        
    print(f"🎉 Successfully built complete Report Mode analysis! Saved to: {report_path}")

if __name__ == "__main__":
    import argparse
    import glob
    import csv

    parser = argparse.ArgumentParser(description="Extract facial metrics from photos")
    parser.add_argument(
        "--mode",
        choices=["calibration", "main", "report"],
        default="calibration",
        help=(
            "calibration — запуск на калибровочном датасете для построения noise model; "
            "main — запуск на основном датасете с учётом калибровочных данных; "
            "report — построение комплексного хронологического отчета"
        ),
    )
    parser.add_argument("--photos-dir", type=str, default=None, help="Папка с фото")
    parser.add_argument("--out-dir",    type=str, default=None, help="Папка для результатов")
    parser.add_argument(
        "--calib-csv",
        type=str,
        default=str(Path(__file__).parent / "calibration_data.csv"),
        help="Путь к calibration_data.csv (используется только в режиме main)",
    )
    parser.add_argument("--limit", type=int, default=None, help="Ограничение на количество обрабатываемых фото")
    args = parser.parse_args()

    # ── Пути по умолчанию ────────────────────────────────────────────────────
    if args.mode == "calibration":
        photos_dir = Path(args.photos_dir or "/Volumes/SDCARD/photo/calibration")
        out_dir    = args.out_dir or "/Volumes/SDCARD/storage/calibration"
    elif args.mode == "main":
        photos_dir = Path(args.photos_dir or "/Volumes/SDCARD/photo/main")
        out_dir    = args.out_dir or "/Volumes/SDCARD/storage/main"
    else:
        photos_dir = Path(args.photos_dir or "/Volumes/SDCARD/photo/main")
        out_dir    = args.out_dir or "/Volumes/SDCARD/storage/main"

    # ── Загрузка калибровочного датафрейма (только для режима main) ─────────
    calib_df = None
    if args.mode == "main":
        calib_csv = Path(args.calib_csv)
        if calib_csv.exists():
            try:
                import pandas as pd
                calib_df = pd.read_csv(calib_csv)
                print(f"[main mode] Loaded calib_df with {len(calib_df)} records from {calib_csv}")
            except Exception as e:
                print(f"Error loading calibration dataframe from {calib_csv}: {e}")
        else:
            print(f"[main mode] WARNING: calibration_data.csv not found at {calib_csv}.")

    # ── Сбор списка фото ─────────────────────────────────────────────────────
    test_photos = sorted(
        glob.glob(str(photos_dir / "*.jpg")) +
        glob.glob(str(photos_dir / "*.jpeg")) +
        glob.glob(str(photos_dir / "*.png"))
    )
    if args.limit is not None:
        test_photos = test_photos[:args.limit]

    print(f"[{args.mode.upper()} MODE] Found {len(test_photos)} photos → {out_dir}")

    if args.mode == "report":
        import sys
        total = len(test_photos)
        ready_photos = []
        for p in test_photos:
            rj = Path(out_dir) / Path(p).stem / "result.json"
            if rj.exists():
                try:
                    with open(rj, "r") as f:
                        data = json.load(f)
                    if data.get("status") == "ready":
                        ready_photos.append(p)
                except Exception:
                    pass
        ready = len(ready_photos)
        if ready < total:
            print(f"⚠️  Не все фото обработаны: {ready}/{total}. Сначала запустите --mode main")
            sys.exit(1)
            
        calib_csv = Path(args.calib_csv)
        import pandas as pd
        calib_df = pd.read_csv(calib_csv) if calib_csv.exists() else None
        
        run_report_mode(test_photos, out_dir, calib_df)
        sys.exit(0)

    # ── Предварительная сборка хронологического индекса ─────────────────────
    from collections import defaultdict
    from backend.core.utils import parse_date_from_name
    import re

    chrono_index = defaultdict(list)
    temp_chrono = defaultdict(list)
    for photo in test_photos:
        photo_stem = Path(photo).stem
        bucket = bucket_from_filename(photo_stem)
        _, date_obj = parse_date_from_name(Path(photo).name)
        if date_obj is None:
            import datetime
            date_obj = datetime.datetime(1900, 1, 1)
        temp_chrono[bucket].append((date_obj, photo_stem))
        
    for bucket, lst in temp_chrono.items():
        sorted_lst = sorted(lst, key=lambda x: x[0])
        chrono_index[bucket] = [x[1] for x in sorted_lst]

    # ── Обработка ────────────────────────────────────────────────────────────
    for photo in test_photos:
        try:
            # Удаляем старый результат для пересчёта
            out_path = Path(out_dir) / Path(photo).stem / "result.json"
            if out_path.exists():
                out_path.unlink()

            result = extract_one(photo, out_dir, mode=args.mode, calib_df=calib_df, chrono_index=chrono_index)

            # Верификация
            if out_path.exists():
                with open(out_path, "r") as f:
                    res_data = json.load(f)
                
                pose_bucket = res_data.get("pose", {}).get("bucket", "unknown")
                geo_metrics = res_data.get("geometry", {}) or {}
                tex_metrics = res_data.get("texture", {}) or {}
                metrics = {**{k: v for k, v in geo_metrics.items() if k != "excluded_zones"},
                           **{k: v for k, v in tex_metrics.items() if k != "excluded_zones"}}
                null_keys = [k for k, v in metrics.items() if v is None]
                
                flagged = []
                if args.mode == "main":
                    calib_flags = res_data.get("calibration", {}).get("metrics", {}) or {}
                    flagged = [
                        k for k, v in calib_flags.items()
                        if isinstance(v, dict) and v.get("flagged")
                    ]
                
                print(
                    f"✅ {Path(photo).name} | bucket={pose_bucket} "
                    f"| metrics={len(metrics)} | nulls={len(null_keys)}"
                    + (f" | flagged={len(flagged)}" if args.mode == "main" else "")
                )
        except Exception as err:
            print(f"❌ {Path(photo).name}: {err}")

    # ── Сборка пар калибровки (только для режима calibration) ──────────────────────
    if False and args.mode == "calibration":
        print("[calibration mode] Processing all-pairs calibration and building calibration_pairs.csv...")
        import pandas as pd
        from backend.pipeline.calibration import build_calibration_pairs_csv

        calib_records = []
        for photo in test_photos:
            res_json_path = Path(out_dir) / Path(photo).stem / "result.json"
            if res_json_path.exists():
                try:
                    with open(res_json_path, "r") as f:
                        data = json.load(f)
                    
                    expr = data.get("expression", {}) or {}
                    source = data.get("source", {}) or {}
                    pose = data.get("pose", {}) or {}
                    qual = data.get("quality", {}) or {}
                    calib_records.append({
                        "filename": source.get("filename") or data.get("filename"),
                        "bucket": pose.get("bucket", "frontal"),
                        "mesh_path": str(Path(out_dir) / Path(photo).stem),
                        "pose_yaw": float(pose.get("yaw") or 0.0),
                        "pose_pitch": float(pose.get("pitch") or 0.0),
                        "quality_overall": float(qual.get("overall") or 0.7),
                        "expression_mouth_open_intensity": float(expr.get("mouth_open_intensity") or 0.0),
                        "expression_smile_intensity": float(expr.get("smile_intensity") or 0.0),
                    })
                except Exception as e:
                    print(f"Error reading result for {Path(photo).name}: {e}")

        if calib_records:
            calib_df = pd.DataFrame(calib_records)
            pairs_csv_path = Path(out_dir) / "calibration_pairs.csv"
            try:
                build_calibration_pairs_csv(calib_df, Path(out_dir), pairs_csv_path)
                print(f"✅ Successful calibration run! Saved {len(calib_df)} photos and built calibration pairs CSV at {pairs_csv_path}")
            except Exception as e:
                print(f"Error building calibration pairs: {e}")

    # --- Сборка единой flat CSV со всеми метриками для обоих режимов ---
    flat_records = []
    if False:
        print(f"[{args.mode} mode] Building consolidated calibration_data.csv with all metrics...")
        import pandas as pd
    for photo in []:
        res_json_path = Path(out_dir) / Path(photo).stem / "result.json"
        if res_json_path.exists():
            try:
                with open(res_json_path, "r") as f:
                    data = json.load(f)
                
                source = data.get("source", {}) or {}
                pose = data.get("pose", {}) or {}
                qual = data.get("quality", {}) or {}
                expr = data.get("expression", {}) or {}
                geo = data.get("geometry", {}) or {}
                tex = data.get("texture", {}) or {}
                
                flat_row = {
                    "filename": source.get("filename") or data.get("filename"),
                    "pose_bucket": pose.get("bucket", "frontal"),
                    "pose_yaw": pose.get("yaw", 0.0),
                    "pose_pitch": pose.get("pitch", 0.0),
                    "pose_roll": pose.get("roll", 0.0),
                    "quality_overall": qual.get("overall", 0.7),
                    "quality_sharpness": qual.get("sharpness", 0.0),
                    "quality_blur": qual.get("blur", 0.0),
                    "quality_jpeg_noise": qual.get("jpeg_noise", 0.0),
                    "expression_mouth_open_intensity": expr.get("mouth_open_intensity", 0.0),
                    "expression_smile_intensity": expr.get("smile_intensity", 0.0),
                    "mesh_path": str(Path(out_dir) / Path(photo).stem),
                }
                for k, v in geo.items():
                    if k != "excluded_zones":
                        flat_row[f"geo_{k}"] = v
                for k, v in tex.items():
                    if k == "excluded_zones":
                        continue
                    if k != "quality":
                        flat_row[f"tex_{k}"] = v
                    else:
                        for qk, qv in (v or {}).items():
                            flat_row[f"tex_quality_{qk}"] = qv
                            
                flat_records.append(flat_row)
            except Exception as e:
                print(f"Error flattening result for {Path(photo).name}: {e}")
                
    if flat_records:
        flat_df = pd.DataFrame(flat_records)
        csv_filename = "main_data.csv" if args.mode == "main" else "calibration_data.csv"
        flat_csv_path = Path(out_dir) / csv_filename
        try:
            flat_df.to_csv(flat_csv_path, index=False)
            print(f"✅ Created consolidated flat CSV with all metrics at: {flat_csv_path}")
        except Exception as e:
            print(f"Error saving consolidated flat CSV: {e}")
