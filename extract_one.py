
import os
import sys
import json
import shutil
import traceback
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
import numpy as np

import sys
sys.path.insert(0, "/Users/victorkhudyakov/dutin/core/3ddfa_v3")
sys.path.insert(0, "/Users/victorkhudyakov/dutin/newapp")
import json
import test_single_photo.process_single_photo_v2 as psp
from PIL import Image

def extract_one(photo_path_str, out_root_dir_str):
    photo_path = Path(photo_path_str)
    photo_name = photo_path.stem
    out_dir = Path(out_root_dir_str) / photo_name
    out_dir.mkdir(parents=True, exist_ok=True)
    
    psp.INPUT_PHOTO = str(photo_path)
    psp.OUTPUT_DIR = out_dir
    psp.SKIP_RAW_SUBDIR = True
    errors = []
    
    print(f"Start processing: {photo_name}")
    
    try:
        img, img_info = psp.load_and_validate_image(psp.INPUT_PHOTO)
        
        # Create original and thumbnail directly in out_dir
        img.convert("RGB").save(out_dir / "original.jpg", "JPEG", quality=95)
        
        orig_w, orig_h = img.size
        new_h = 50
        new_w = int(orig_w * (new_h / orig_h))
        img.copy().resize((new_w, new_h), Image.Resampling.LANCZOS).save(out_dir / "thumbnail.jpg", "JPEG", quality=85)
        
        quality_metrics = psp.estimate_quality_metrics(np.array(img.convert("RGB")))
        recon_data = psp.extract_reconstruction_data(psp.INPUT_PHOTO)
        
        if not recon_data["success"]:
            errors.append("3DDFA extraction failed")
            bbox_result = {"success": False, "error": "3DDFA failed"}
            pose_3ddfa = {"success": False}
            reconstruction = {"success": False}
        else:
            bbox_result = recon_data["bbox"]
            pose_3ddfa = recon_data["pose"]
            reconstruction = recon_data["reconstruction"]
            
            # Save mesh inside out_dir directly
            np.save(out_dir / "vertices.npy", np.array(reconstruction["vertices"]))
            with open(out_dir / "face_mesh.obj", 'w') as f:
                 for v in reconstruction["vertices"]:
                     f.write(f"v {v[0]} {v[1]} {v[2]}\n")
                 for t in reconstruction["triangles"]:
                     f.write(f"f {t[0]+1} {t[1]+1} {t[2]+1}\n")
            
            # --- Generate PERFECT UVs using uv_module with original image mapping ---
            from pipeline.reconstruction import ReconstructionAdapter
            import cv2
            from uv_module.hd_uv_generator import HDUVTextureGenerator, HDUVConfig
            
            adapter = ReconstructionAdapter()
            res = adapter.reconstruct(Path(psp.INPUT_PHOTO))
            
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
                
            verts_3d = getattr(res, "vertices_camera", res.vertices_world).copy()
            verts_3d[:, 2] = -verts_3d[:, 2]  # Fix Z-buffer occlusion: 3DDFA has +Z towards camera, but Z-buffer expects -Z towards camera
            
            recon_dict_for_uv = {
                "vertices": res.vertices_world,
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
            cv2.imwrite(uv_path, cv2.cvtColor(uv_tex_beauty, cv2.COLOR_RGB2BGR), [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            
            # --- Generate robust fallback mask using 3D normals (exactly like process_single_photo_v2.py) ---
            uv_res = 1024
            uv_mask = np.zeros((uv_res, uv_res), dtype=np.uint8)
            uv_coords_img = np.zeros_like(res.uv_coords)
            uv_coords_img[:, 0] = res.uv_coords[:, 0] * (uv_res - 1)
            uv_coords_img[:, 1] = (1.0 - res.uv_coords[:, 1]) * (uv_res - 1)
            uv_coords_scaled = uv_coords_img.astype(np.int32)
            # Apply power (gamma = 4.0) to make oblique angles (cheeks) darker with a sharper transition
            confidence_per_vertex = np.power(np.clip(res.normals_camera[:, 2], 0, 1), 4.0) * 255
            for tri in res.triangles:
                pts = uv_coords_scaled[tri]
                mean_conf = int(np.mean(confidence_per_vertex[tri]))
                if mean_conf > 0:
                    cv2.fillConvexPoly(uv_mask, pts[:, :2], mean_conf)
            # Use smaller Gaussian blur kernel (5x5 instead of 15x15) for sharper transition
            uv_confidence_mask = cv2.GaussianBlur(cv2.dilate(uv_mask, np.ones((3,3), np.uint8)), (5, 5), 0)
            
            uv_mask_path = str(out_dir / "uv_confidence_mask.jpg")
            cv2.imwrite(uv_mask_path, uv_confidence_mask, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            
            reconstruction["uv_texture_path"] = uv_path
            reconstruction["uv_confidence_mask_path"] = uv_mask_path
            reconstruction["uv_raw"] = uv_tex_beauty
            reconstruction["uv_confidence_mask"] = uv_confidence_mask
                     
        masked_full, masked_face, refined_bbox = psp.apply_segmentation_mask(img, recon_data)
        if refined_bbox.get("success"):
            bbox_result = refined_bbox
            
        pose_hpe = psp.extract_pose_hpe(psp.INPUT_PHOTO, external_bbox=bbox_result)
        
        if pose_hpe["success"]:
            pose_result = pose_hpe
        elif pose_3ddfa.get("success"):
            pose_result = pose_3ddfa
        else:
            pose_result = {"success": False, "yaw": None, "pitch": None, "roll": None, 
                           "pose_source": "none", "pose_classification": "unknown"}
            errors.append("All pose detection methods failed")
            
        face_stats = psp.compute_face_stats(masked_face, bbox_result)
        
        texture_preds, texture_actual, texture_notes = psp.compute_texture_metrics(
            masked_face, bbox_result, face_stats, 
            uv_texture=reconstruction.get("uv_raw"),
            uv_confidence_mask=reconstruction.get("uv_confidence_mask")
        )
        
        geometric = psp.compute_geometric_metrics(reconstruction, pose_result)
        
        result = psp.ProcessingResult(
            photo_path=psp.INPUT_PHOTO,
            filename=Path(psp.INPUT_PHOTO).name,
            timestamp=datetime.now().isoformat(),
            image_width=img_info["width"],
            image_height=img_info["height"],
            image_format=img_info["format"] or "PNG",
            image_mode=img_info["mode"],
            pose_yaw=pose_result.get("yaw"),
            pose_pitch=pose_result.get("pitch"),
            pose_roll=pose_result.get("roll"),
            pose_source=pose_result.get("pose_source", "none"),
            pose_classification=pose_result.get("pose_classification", "unknown"),
            bbox_x=bbox_result.get("x"),
            bbox_y=bbox_result.get("y"),
            bbox_w=bbox_result.get("w"),
            bbox_h=bbox_result.get("h"),
            bbox_score=bbox_result.get("score"),
            bbox_kp5=bbox_result.get("kp5", []),
            face_mean_lum=face_stats.get("meanLum") if face_stats.get("success") else None,
            face_std_lum=face_stats.get("stdLum") if face_stats.get("success") else None,
            face_mean_r=face_stats.get("meanR") if face_stats.get("success") else None,
            face_mean_g=face_stats.get("meanG") if face_stats.get("success") else None,
            face_mean_b=face_stats.get("meanB") if face_stats.get("success") else None,
            face_std_r=face_stats.get("stdR") if face_stats.get("success") else None,
            face_std_g=face_stats.get("stdG") if face_stats.get("success") else None,
            face_std_b=face_stats.get("stdB") if face_stats.get("success") else None,
            quality_blur=quality_metrics.get("blur_value") if quality_metrics.get("success") else None,
            quality_sharpness=quality_metrics.get("sharpness_value") if quality_metrics.get("success") else None,
            quality_jpeg=quality_metrics.get("jpeg_blockiness") if quality_metrics.get("success") else None,
            quality_overall=quality_metrics.get("overall_quality") if quality_metrics.get("success") else None,
            reconstruction_success=reconstruction.get("success", False),
            vertices_count=reconstruction.get("vertices_count"),
            triangles_count=reconstruction.get("triangles_count"),
            mesh_path=str(out_dir) if reconstruction.get("success") else None,
            uv_texture_path=str(out_dir / "uv_texture_hd.jpg") if reconstruction.get("success") else None,
            uv_normalized_path=str(out_dir / "uv_normalized.jpg") if reconstruction.get("uv_normalized_path") else None,
            uv_confidence_mask_path=str(out_dir / "uv_confidence_mask.jpg") if reconstruction.get("success") else None,
            segmented_face_path=str(out_dir / "face_crop.jpg"),
            texture_predictions=texture_preds,
            texture_actual=texture_actual,
            texture_analysis_notes=texture_notes,
            geometric_metrics=geometric,
            errors=errors
        )
        
        result_dict = asdict(result)
        if "texture_predictions" in result_dict:
            del result_dict["texture_predictions"]
        
        with open(out_dir / "result.json", 'w') as f:
            json.dump(result_dict, f, indent=2, default=str)
            
        print(f"Finished extracting ONE photo: {photo_name}")
        
    except Exception as e:
        print(f"Error processing {photo_name}: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    # Test on a single frontal image exactly as requested
    test_img = "/Volumes/SDCARD/photo/calibration/calibration_y3p-3r2.jpg"
    extract_one(test_img, "/Volumes/SDCARD/storage/calibration")
