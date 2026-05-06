from __future__ import annotations
import json
import logging
from pathlib import Path
import numpy as np

logger = logging.getLogger("deeputin.compare")

class InvestigationEngine:
    def __init__(self, summary_dir: Path):
        self.summary_dir = Path(summary_dir)
        # Загружаем все JSON-векторы в оперативную память (Offline Store)
        self.vectors = self._load_all_summaries()
        
    def _load_all_summaries(self) -> dict:
        data = {}
        # Support both *_summary.json and summary.json in subdirectories recursively
        json_files = list(self.summary_dir.glob("*_summary.json")) + list(self.summary_dir.glob("**/summary.json"))
        seen = set()
        for json_file in json_files:
            resolved = json_file.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
                    photo_id = summary_data.get("photo_id", json_file.parent.name)
                    data[photo_id] = summary_data
            except Exception as e:
                logger.error(f"Error loading summary from {json_file}: {e}")
        return data

    def compute_n_x_n_matrix(self) -> np.ndarray:
        """
        Мгновенное вычисление графа связей без вызова нейросетей.
        Сложность сведена к простым матричным операциям над числами.
        """
        keys = list(self.vectors.keys())
        n = len(keys)
        matrix_h0 = np.zeros((n, n))
        
        for i in range(n):
            for j in range(i + 1, n): # Оптимизация: считаем только верхний треугольник
                vec_a = self.vectors[keys[i]]
                vec_b = self.vectors[keys[j]]
                
                # Защита от краша сериализации: anom['metric_key']
                # Раньше падало из-за обращения к anom['metric']
                try:
                    score = self._compute_bayesian_evidence(vec_a, vec_b)
                    matrix_h0[i][j] = score
                    matrix_h0[j][i] = score # Делаем матрицу симметричной, где применимо
                except KeyError as e:
                    logger.error(f"Ошибка сериализации контракта данных в паре {keys[i]} - {keys[j]}: {e}")
                    matrix_h0[i][j] = np.nan
                    matrix_h0[j][i] = np.nan
                    
        return matrix_h0

    def _compute_bayesian_evidence(self, vec_a: dict, vec_b: dict) -> float:
        from .analysis import calculate_bayesian_evidence
        res = calculate_bayesian_evidence(vec_a, vec_b)
        return float(res.get("H0", 0.95))

    def suspicious_windows(self) -> list[dict]:
        """
        [ITER-1.4] Возвращает подозрительные интервалы/окна аномалий на основе матрицы H0.
        Гарантирует использование metric_key вместо metric во избежание сбоев сериализации.
        """
        anomalies = []
        keys = list(self.vectors.keys())
        matrix_h0 = self.compute_n_x_n_matrix()
        
        # Нахождение сильных просадок H0 (высокая вероятность подмены/аномалии)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                score = matrix_h0[i][j]
                if not np.isnan(score) and score < 0.4:
                    anomalies.append({
                        "photo_a_id": keys[i],
                        "photo_b_id": keys[j],
                        "score_h0": score,
                        "metric_key": "cranial_face_index",  # Жестко фиксируем контракт данных metric_key
                        "reason": "Sudden geometric drop"
                    })
        return anomalies
