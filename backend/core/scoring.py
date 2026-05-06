import numpy as np
from backend.core.utils import BUCKET_METRIC_KEYS

def compute_true_coverage(computed_metrics: dict, pose_bucket: str) -> float:
    """
    Вычисляет истинное покрытие метриками (Coverage Ratio).
    Исправлен баг "искусственного завышения" (M-06).
    """
    # Эталонный список метрик для данного ракурса (НЕ ИЗМЕНЯЕТСЯ!)
    expected_keys = BUCKET_METRIC_KEYS.get(pose_bucket, [])
    if not expected_keys:
        return 0.0
        
    # Считаем только те ключи, которые реально есть и не равны NaN
    valid_count = 0
    for key in expected_keys:
        if key in computed_metrics and computed_metrics[key] is not None and not (isinstance(computed_metrics[key], float) and np.isnan(computed_metrics[key])):
            valid_count += 1
            
    coverage_ratio = valid_count / len(expected_keys)
    return float(coverage_ratio)

def normalize_local_noise(raw_3d_noise: float, face_scale: float) -> float:
    """
    Приводит шкалу калибровочного шума к единому пространству с метриками (M-05).
    """
    # Защита от деления на ноль
    safe_scale = max(face_scale, 1e-6)
    
    # Теперь калибровочный шум измеряется в тех же долях от ширины лица,
    # что и базовая ошибка (raw_error)
    normalized_noise = raw_3d_noise / safe_scale
    return normalized_noise
