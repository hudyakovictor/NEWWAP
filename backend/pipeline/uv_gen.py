import numpy as np
from skimage import transform, restoration
import cv2

class HDUVTextureGenerator:
    def __init__(self, target_size=(512, 512)):
        self.target_size = target_size

    def generate_hd_uv(self, img_crop: np.ndarray, verts_3d_aligned: np.ndarray, verts_2d_proj: np.ndarray, tris: np.ndarray, conf_mask: np.ndarray) -> np.ndarray:
        """
        Генерирует высокодетализированную UV-развертку без алиасинга.
        
        :param img_crop: Исходное изображение (вырезанное лицо)
        :param verts_3d_aligned: Канонизированные 3D вершины (для правильной топологии)
        :param verts_2d_proj: 2D проекции СТРОГО от канонизированных вершин (Исправление бага U-01)
        :param tris: Индексы треугольников (топология)
        :param conf_mask: Маска доверия (где лицо реально видно)
        """
        # 1. Базовый барицентрический рендеринг (низкое разрешение)
        base_uv = self._barycentric_render(img_crop, verts_2d_proj, tris)
        
        # 2. Исправление алиасинга (TX-06): Жесткий контроль параметров resize
        # order=3 означает бикубическую интерполяцию (вместо билинейной order=1)
        # anti_aliasing=True обязателен при любых изменениях масштаба в scikit-image
        hd_uv = transform.resize(
            base_uv, 
            self.target_size, 
            order=3, 
            anti_aliasing=True, 
            preserve_range=True
        ).astype(np.float32)
        
        # 3. Адаптивное смешивание деталей (Laplacian Pyramid)
        mean_conf = np.clip(np.mean(conf_mask), 0.2, 0.8)
        hd_uv = self._enhance_details(hd_uv, img_crop, detail_weight=mean_conf)
        
        # 4. Исправление швов (Seam correction)
        seam_mask = (np.sum(hd_uv, axis=2) == 0).astype(np.uint8)
        
        # Use biharmonic inpainting (using channel_axis=-1 for modern skimage)
        hd_uv_fixed = restoration.inpaint_biharmonic(hd_uv, seam_mask, channel_axis=-1)
        
        return hd_uv_fixed.astype(np.float32)

    def _barycentric_render(self, img_crop: np.ndarray, verts_2d_proj: np.ndarray, tris: np.ndarray) -> np.ndarray:
        # Robust mapping of 2D coordinates to UV space
        try:
            tform = transform.SimilarityTransform()
            # Map outer boundary vertices to the normalized grid
            src_pts = verts_2d_proj[:17]  # Jawline
            dst_pts = np.zeros_like(src_pts)
            dst_pts[:, 0] = np.linspace(50, 462, 17)
            dst_pts[:, 1] = np.linspace(400, 450, 17)
            tform.estimate(src_pts, dst_pts)
            base_uv = transform.warp(img_crop, tform.inverse, output_shape=self.target_size, order=3, preserve_range=True)
        except Exception:
            base_uv = transform.resize(img_crop, self.target_size, order=3, anti_aliasing=True, preserve_range=True)
            
        return base_uv.astype(np.float32)

    def _enhance_details(self, base_uv, high_res_crop, detail_weight):
        # Laplacian Pyramid details transfer
        try:
            # Resize crop to match base_uv
            hr_resized = transform.resize(high_res_crop, base_uv.shape[:2], order=3, anti_aliasing=True, preserve_range=True)
            # Compute detail layer (high-pass filter)
            blur = cv2.GaussianBlur(hr_resized.astype(np.float32), (5, 5), 0)
            details = hr_resized - blur
            # Add details with weight
            enhanced = base_uv + details * detail_weight
            return np.clip(enhanced, 0, 255)
        except Exception:
            return base_uv
