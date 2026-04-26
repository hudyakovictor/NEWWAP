from __future__ import annotations

import numpy as np
from typing import Any, List, Dict
from collections import defaultdict
from .utils import BUCKET_METRIC_KEYS

def cluster_personas(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    [PERS-01] Кластеризация масок/персон.
    Группирует фотографии с похожим профилем геометрических аномалий.
    Это позволяет выявить использование одного и того же реквизита (маски) в разные годы.
    """
    if not records:
        return []

    # Группируем по бакетам (ракурсам) для корректного сравнения
    by_bucket = defaultdict(list)
    for r in records:
        by_bucket[r.get("bucket")].append(r)

    persona_groups = []
    
    for bucket, bucket_records in by_bucket.items():
        if len(bucket_records) < 2:
            continue
            
        keys = BUCKET_METRIC_KEYS.get(bucket, [])
        if not keys:
            continue

        # Векторизуем метрики
        vectors = []
        valid_records = []
        for r in bucket_records:
            m = r.get("metrics", {})
            vec = [m.get(k, 0.0) for k in keys if not k.startswith("texture_")]
            if vec:
                vectors.append(vec)
                valid_records.append(r)
        
        if not vectors:
            continue

        # Очень простая кластеризация на основе евклидова расстояния
        # В будущем можно использовать DBSCAN
        data = np.array(vectors)
        # Нормализуем по колонкам
        mins = data.min(axis=0)
        maxs = data.max(axis=0)
        denom = maxs - mins
        denom[denom == 0] = 1.0
        norm_data = (data - mins) / denom

        # Поиск "сигнатур" (близких векторов)
        # Если расстояние < 0.15 (15% от размаха), считаем одной персоной
        assigned = [False] * len(valid_records)
        for i in range(len(valid_records)):
            if assigned[i]: continue
            
            current_cluster = [valid_records[i]]
            assigned[i] = True
            
            for j in range(i + 1, len(valid_records)):
                if assigned[j]: continue
                dist = np.linalg.norm(norm_data[i] - norm_data[j])
                if dist < 0.2: # Порог схожести
                    current_cluster.append(valid_records[j])
                    assigned[j] = True
            
            if len(current_cluster) > 1:
                # Нашли повторяющуюся сигнатуру
                persona_groups.append({
                    "persona_id": f"persona_{len(persona_groups)}_{bucket}",
                    "bucket": bucket,
                    "count": len(current_cluster),
                    "photo_ids": [r["photo_id"] for r in current_cluster],
                    "avg_profile": {k: float(np.mean([r["metrics"].get(k, 0.0) for r in current_cluster])) for k in keys}
                })

    return persona_groups
