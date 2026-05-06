from skimage import transform
import numpy as np

def compute_procrustes_symmetry(uv_texture: np.ndarray, lm_left: np.ndarray, lm_right: np.ndarray, conf_mask: np.ndarray) -> float:
    """
    Вычисляет симметрию текстуры, предварительно выравнивая левую и правую половины лица 
    по ключевым точкам (Landmarks) через Прокрустово выравнивание 2D.
    
    :param uv_texture: HD UV развертка (512, 512, 3)
    :param lm_left: Координаты точек левой половины лица на UV
    :param lm_right: Координаты точек правой половины лица на UV
    """
    # 1. Оцениваем аффинную матрицу смещения (Translation + Rotation + Scale)
    # Пытаемся "натянуть" правую половину на левую для компенсации природной кривизны
    tform = transform.SimilarityTransform()
    tform.estimate(lm_right, lm_left) 
    
    # 2. Искажаем ВСЮ текстуру согласно найденной трансформации (кубическая интерполяция)
    uv_aligned = transform.warp(
        uv_texture, 
        tform, 
        output_shape=uv_texture.shape[:2], 
        order=3, # Кубическая интерполяция для защиты от алиасинга
        preserve_range=True
    )
    
    # 3. Только теперь мы можем безопасно сделать зеркальное отражение
    # Т.к. геометрический центр смещен в истинный центр масс лица
    uv_flip = np.fliplr(uv_aligned)
    
    # 4. Вычисляем разницу только в зонах с высоким уровнем доверия (conf_mask)
    # Используем L1 норму (Absolute Difference) для устойчивости к бликам
    diff_map = np.abs(uv_texture - uv_flip)
    
    # Применяем маску кожи/доверия
    valid_diffs = diff_map[conf_mask > 0.65]
    
    if len(valid_diffs) == 0:
        return np.nan
        
    # Симметрия: 1.0 - это идеал, 0.0 - полная асимметрия
    max_possible_diff = 255.0 if uv_texture.dtype == np.uint8 else 1.0
    symmetry_score = 1.0 - (np.mean(valid_diffs) / max_possible_diff)
    
    return float(symmetry_score)


def compute_symmetry_distance_map(skin_regions_mask: np.ndarray) -> np.ndarray:
    """
    Вычисляет карту расстояний внутри маски лица.
    Исправлен баг инверсии ~mask (TX-05).
    """
    from scipy import ndimage
    # Гарантируем, что маска бинарная (1 - лицо, 0 - фон)
    binary_mask = (skin_regions_mask > 0).astype(np.uint8)
    
    # Считаем точное Евклидово расстояние (distance=2 в некоторых реализациях, 
    # в scipy edt это поведение по умолчанию).
    # УБРАНА инверсия ~binary_mask. Теперь 0 на фоне остается 0, 
    # а внутри лица дистанция растет к центру.
    dist_map = ndimage.distance_transform_edt(binary_mask)
    
    return dist_map
