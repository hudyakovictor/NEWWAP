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

def extract_one(photo_path_str, out_root_dir_str):
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
        np.save(out_dir / "vertices.npy", np.array(res.vertices_world))
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
            out_dir / "face_crop.png",
            uv_path=Path(uv_path),
            uv_mask_path=Path(uv_mask_path)
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
                    # Текстурные метрики будут удалены ниже в блоке текстур
                ]
                for metric_key in compromised_smile_metrics:
                    if metric_key in geo_metrics:
                        geo_metrics[metric_key] = None

        geometric = geo_metrics
        
        parsed_year = None
        try:
            from backend.core.utils import parse_date_from_name
            parsed_date = parse_date_from_name(photo_path.name)
            if parsed_date:
                parsed_year = int(parsed_date.split("-")[0])
        except Exception:
            pass

        result = {
            "photo_path": str(photo_path),
            "filename": photo_path.name,
            "timestamp": datetime.now().isoformat(),
            "parsed_year": parsed_year,
            "image_width": img_info["width"],
            "image_height": img_info["height"],
            "image_format": img_info["format"] or "JPEG",
            "image_mode": img_info["mode"],
            "pose_yaw": pose_result.get("yaw"),
            "pose_pitch": pose_result.get("pitch"),
            "pose_roll": pose_result.get("roll"),
            "pose_source": pose_result.get("pose_source", "none"),
            "pose_classification": pose_result.get("pose_classification", "unknown"),
            "bbox_x": bbox_result.get("x"),
            "bbox_y": bbox_result.get("y"),
            "bbox_w": bbox_result.get("w"),
            "bbox_h": bbox_result.get("h"),
            "bbox_score": bbox_result.get("score"),
            "bbox_kp5": bbox_result.get("kp5", []),
            "face_mean_lum": face_stats.get("meanLum") if face_stats.get("success") else None,
            "face_std_lum": face_stats.get("stdLum") if face_stats.get("success") else None,
            "face_mean_r": face_stats.get("meanR") if face_stats.get("success") else None,
            "face_mean_g": face_stats.get("meanG") if face_stats.get("success") else None,
            "face_mean_b": face_stats.get("meanB") if face_stats.get("success") else None,
            "face_std_r": face_stats.get("stdR") if face_stats.get("success") else None,
            "face_std_g": face_stats.get("stdG") if face_stats.get("success") else None,
            "face_std_b": face_stats.get("stdB") if face_stats.get("success") else None,
            "quality_blur": quality_metrics.get("blur_value") if quality_metrics.get("success") else None,
            "quality_sharpness": quality_metrics.get("sharpness_value") if quality_metrics.get("success") else None,
            "quality_jpeg": quality_metrics.get("jpeg_blockiness") if quality_metrics.get("success") else None,
            "quality_overall": quality_metrics.get("overall_quality") if quality_metrics.get("success") else None,
            "reconstruction_success": reconstruction.get("success", False),
            "vertices_count": reconstruction.get("vertices_count"),
            "triangles_count": reconstruction.get("triangles_count"),
            "mesh_path": str(out_dir) if reconstruction.get("success") else None,
            "uv_texture_path": str(out_dir / "uv_texture_hd.jpg") if reconstruction.get("success") else None,
            "uv_confidence_mask_path": str(out_dir / "uv_confidence_mask.jpg") if reconstruction.get("success") else None,
            "segmented_face_path": str(out_dir / "face_crop.png"),
            "texture_predictions": texture_preds,
            "texture_actual": texture_actual,
            "texture_analysis_notes": texture_notes,
            "geometric_metrics": geometric,
            "errors": errors
        }
        
        from core.utils import RAW_BUCKET_TO_UI
        bucket = pose_class
        bucket_ui = RAW_BUCKET_TO_UI.get(bucket, "unknown")

        result_dict = dict(result)
        result_dict["bucket"] = bucket
        result_dict["pose_bucket"] = bucket
        result_dict["bucket_ui"] = bucket_ui
        result_dict["status"] = "ready"
        result_dict["reliability_weight"] = round(float(reliability), 3)
        
        # --- Extract expression and smile parameters ---
        exp_params = res.payload.get("exp_params") if hasattr(res, "payload") and isinstance(res.payload, dict) else None
        jaw_open_val = 0.0
        smile_val = 0.0
        if exp_params is not None and len(exp_params) >= 3:
            jaw_open_val = float(abs(exp_params[0]))
            smile_val = float(max(abs(exp_params[1]), abs(exp_params[2])))
            
        result_dict["expression"] = {
            "mouth_open_intensity": round(jaw_open_val, 4),
            "smile_intensity": round(smile_val, 4),
            "is_mouth_open_detected": jaw_open_val > 0.12,
            "is_smile_detected": smile_val > 0.08
        }
        
        # Ensure metrics dictionary exists and is populated with geometric and texture metrics
        if "metrics" not in result_dict or not isinstance(result_dict["metrics"], dict):
            result_dict["metrics"] = {}
            
        if isinstance(geometric, dict):
            result_dict["metrics"].update(geometric)
            
        if isinstance(texture_preds, dict):
            # Mask forehead wrinkles when head yaw exceeds 30 degrees to avoid pose bias
            forehead_wrinkle_val = texture_preds.get("wrinkle_forehead", 0.0)
            if abs(yaw) > 30.0:
                forehead_wrinkle_val = None
                texture_preds["wrinkle_forehead"] = None
                
            result_dict["metrics"].update({
                "texture_studio_lighting": texture_preds.get("studio_lighting_score", 0.0),
                "texture_retouch":         texture_preds.get("retouch_score", 0.0),
                "texture_lbp_complexity":  texture_preds.get("lbp_complexity", 0.0),
                "texture_specular_gloss":  texture_preds.get("specular_gloss", 0.0),
                "texture_spot_density":    texture_preds.get("spot_density", 0.0),
                "texture_wrinkle_forehead": forehead_wrinkle_val,
            })
        
        from backend.core.utils import BUCKET_METRIC_KEYS as _BMK
        _bucket = result_dict.get("pose_bucket", "unclassified")
        _expected = _BMK.get(_bucket, [])
        _present = [k for k in _expected
                    if result_dict.get("metrics", {}).get(k) is not None]
        result_dict["bucket_metrics_coverage"] = (
            round(len(_present) / len(_expected), 3) if _expected else 0.0
        )

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

if __name__ == "__main__":
    import argparse
    import glob
    import csv

    parser = argparse.ArgumentParser(description="Extract facial metrics from photos")
    parser.add_argument(
        "--mode",
        choices=["calibration", "main"],
        default="calibration",
        help=(
            "calibration — запуск на калибровочном датасете для построения noise model; "
            "main — запуск на основном датасете с учётом калибровочных данных"
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
    args = parser.parse_args()

    # ── Пути по умолчанию ────────────────────────────────────────────────────
    if args.mode == "calibration":
        photos_dir = Path(args.photos_dir or "/Volumes/SDCARD/photo/calibration")
        out_dir    = args.out_dir or "/Volumes/SDCARD/storage/calibration"
    else:
        photos_dir = Path(args.photos_dir or "/Volumes/SDCARD/photo/main")
        out_dir    = args.out_dir or "/Volumes/SDCARD/storage/main"

    # ── Загрузка калибровочных норм (только для режима main) ─────────────────
    calibration_norms: dict = {}
    if args.mode == "main":
        calib_csv = Path(args.calib_csv)
        if calib_csv.exists():
            with open(calib_csv, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    metric = row.get("metric") or row.get("zone")
                    if metric:
                        calibration_norms[metric] = {
                            "mean":        float(row.get("mean", 0.0)),
                            "std":         float(row.get("std",  0.015)),
                            "pose_bucket": row.get("pose_bucket", "frontal"),
                        }
            print(f"[main mode] Loaded {len(calibration_norms)} calibration norms from {calib_csv}")
        else:
            print(f"[main mode] WARNING: calibration_data.csv not found at {calib_csv}. "
                  f"Run '--mode calibration' first and approve the results.")

    # ── Сбор списка фото ─────────────────────────────────────────────────────
    test_photos = sorted(
        glob.glob(str(photos_dir / "*.jpg")) +
        glob.glob(str(photos_dir / "*.jpeg")) +
        glob.glob(str(photos_dir / "*.png"))
    )
    if not test_photos:
        print(f"No photos found in {photos_dir}")
        sys.exit(1)

    print(f"[{args.mode.upper()} MODE] Found {len(test_photos)} photos → {out_dir}")

    # ── Обработка ────────────────────────────────────────────────────────────
    for photo in test_photos:
        try:
            # Удаляем старый результат для пересчёта
            out_path = Path(out_dir) / Path(photo).stem / "result.json"
            if out_path.exists():
                out_path.unlink()

            result = extract_one(photo, out_dir)

            # В режиме main — обогащаем результат калибровочными нормами
            if args.mode == "main" and calibration_norms and out_path.exists():
                with open(out_path, "r") as f:
                    res_data = json.load(f)

                metrics = res_data.get("metrics", {})
                pose_bucket = res_data.get("pose_bucket", "frontal")
                calibrated_flags = {}

                for metric, value in metrics.items():
                    if value is None:
                        continue
                    norm_key = f"{pose_bucket}_{metric}"
                    norm = calibration_norms.get(norm_key) or calibration_norms.get(metric)
                    if norm:
                        deviation = abs(value - norm["mean"]) / (norm["std"] + 1e-9)
                        calibrated_flags[metric] = {
                            "value":     value,
                            "norm_mean": norm["mean"],
                            "norm_std":  norm["std"],
                            "z_score":   round(deviation, 3),
                            "flagged":   deviation > 2.5,
                        }

                res_data["calibrated_flags"] = calibrated_flags
                res_data["calibration_mode"] = "main"
                res_data["calib_norms_loaded"] = len(calibration_norms)

                with open(out_path, "w") as f:
                    json.dump(res_data, f, ensure_ascii=False, indent=2)

            # Верификация
            if out_path.exists():
                with open(out_path, "r") as f:
                    res_data = json.load(f)
                metrics   = res_data.get("metrics", {})
                null_keys = [k for k, v in metrics.items() if v is None]
                flagged   = []
                if args.mode == "main":
                    flagged = [
                        k for k, v in res_data.get("calibrated_flags", {}).items()
                        if isinstance(v, dict) and v.get("flagged")
                    ]
                print(
                    f"✅ {Path(photo).name} | bucket={res_data.get('pose_bucket')} "
                    f"| metrics={len(metrics)} | nulls={len(null_keys)}"
                    + (f" | flagged={len(flagged)}" if args.mode == "main" else "")
                )

        except Exception as err:
            print(f"❌ {Path(photo).name}: {err}")
