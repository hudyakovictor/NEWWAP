from skimage import transform
import numpy as np
from skimage.feature import local_binary_pattern

def compute_procrustes_symmetry(uv_texture: np.ndarray, lm_left: np.ndarray, lm_right: np.ndarray, conf_mask: np.ndarray) -> float:
    """
    Вычисляет симметрию текстуры, предварительно выравнивая левую и правую половины лица 
    по ключевым точкам (Landmarks) через Прокрустово выравнивание 2D.
    
    :param uv_texture: HD UV развертка (512, 512, 3)
    :param lm_left: Координаты точек левой половины лица на UV
    :param lm_right: Координаты точек правой половины лица на UV
    """
    # 1. [BUGFIX-5] Зеркалируем правую половину лица перед выравниванием
    # Это необходимо для корректного сравнения левой и правой половин
    # Отражаем по оси X (горизонтально) в UV пространстве
    uv_width = uv_texture.shape[1]
    lm_right_mirrored = lm_right.copy()
    lm_right_mirrored[:, 0] = uv_width - lm_right_mirrored[:, 0]
    
    # 2. Оцениваем аффинную матрицу смещения (Translation + Rotation + Scale)
    # Пытаемся "натянуть" зеркальную правую половину на левую для компенсации природной кривизны
    tform = transform.SimilarityTransform()
    tform.estimate(lm_right_mirrored, lm_left) 
    
    # 2. Искажаем ВСЮ текстуру согласно найденной трансформации
    # [BUGFIX-12] Используем линейную интерполяцию (order=1) вместо кубической (order=3)
    # Кубическая интерполяция создает артефакты на границах и бинарных масках
    uv_aligned = transform.warp(
        uv_texture, 
        tform, 
        output_shape=uv_texture.shape[:2], 
        order=1,  # Линейная интерполяция - более стабильна, меньше артефактов
        preserve_range=True
    )
    
    # 3. [BUGFIX-5] После выравнивания с зеркалированными landmarks,
    # выровненная текстура уже имеет зеркальную правую половину в позиции левой.
    # Дополнительное зеркалирование не требуется - сравниваем напрямую.
    # uv_flip = np.fliplr(uv_aligned)  # Убрано - избыточное после зеркалирования lm
    
    # 4. Вычисляем разницу только в зонах с высоким уровнем доверия (conf_mask)
    # [BUGFIX-2] Принудительное приведение типов для избежания uint8 underflow
    # Пример: 10 - 250 в uint8 = 16 (переполнение), что ломает симметрию
    diff_map = np.abs(uv_texture.astype(np.float32) - uv_aligned.astype(np.float32))
    
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


def compute_shadow_lbp_analysis(image: np.ndarray, mask: np.ndarray | None = None) -> dict:
    """
    [BUGFIX-21] Анализ теней с использованием Local Binary Patterns (LBP).
    LBP позволяет обнаруживать аномалии в освещении, которые могут указывать на маску.
    
    :param image: Входное изображение (grayscale или RGB)
    :param mask: Маска лица (опционально)
    :return: Словарь с метриками LBP
    """
    # Конвертируем в grayscale если нужно
    if len(image.shape) == 3:
        gray = np.mean(image, axis=2)
    else:
        gray = image
    
    # Параметры LBP
    radius = 3
    n_points = 8 * radius
    
    # Вычисляем LBP
    lbp = local_binary_pattern(gray, n_points, radius, method='uniform')
    
    # Применяем маску если есть
    if mask is not None:
        if len(mask.shape) == 3:
            mask = np.mean(mask, axis=2)
        lbp = lbp[mask > 0.5]
    else:
        lbp = lbp.flatten()
    
    # Вычисляем гистограмму LBP
    hist, _ = np.histogram(lbp, bins=n_points + 2, range=(0, n_points + 2), density=True)
    
    # Метрики теней
    lbp_variance = float(np.var(lbp))
    lbp_entropy = float(-np.sum(hist * np.log(hist + 1e-10)))
    lbp_uniformity = float(hist[0])  # Доля uniform паттернов (тени)
    
    return {
        "lbp_variance": lbp_variance,
        "lbp_entropy": lbp_entropy,
        "lbp_uniformity": lbp_uniformity,
        "lbp_histogram": hist.tolist()
    }
