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

    def compute_n_x_n_matrix(self) -> dict:
        """
        Мгновенное вычисление графа связей без вызова нейросетей.
        Сложность сведена к простым матричным операциям над числами.
        [BUGFIX] Возвращает словарь с матрицами H0, H1, H2 вместо одной матрицы H0.
        """
        keys = list(self.vectors.keys())
        n = len(keys)
        matrix_h0 = np.zeros((n, n))
        matrix_h1 = np.zeros((n, n))
        matrix_h2 = np.zeros((n, n))
        
        for i in range(n):
            for j in range(i + 1, n): # Оптимизация: считаем только верхний треугольник
                vec_a = self.vectors[keys[i]]
                vec_b = self.vectors[keys[j]]
                
                try:
                    scores = self._compute_bayesian_evidence(vec_a, vec_b)
                    matrix_h0[i][j] = scores["H0"]
                    matrix_h0[j][i] = scores["H0"]
                    matrix_h1[i][j] = scores["H1"]
                    matrix_h1[j][i] = scores["H1"]
                    matrix_h2[i][j] = scores["H2"]
                    matrix_h2[j][i] = scores["H2"]
                except (KeyError, TypeError) as e:
                    logger.error(f"Ошибка сериализации контракта данных в паре {keys[i]} - {keys[j]}: {e}")
                    matrix_h0[i][j] = np.nan
                    matrix_h0[j][i] = np.nan
                    matrix_h1[i][j] = np.nan
                    matrix_h1[j][i] = np.nan
                    matrix_h2[i][j] = np.nan
                    matrix_h2[j][i] = np.nan
                    
        return {"H0": matrix_h0, "H1": matrix_h1, "H2": matrix_h2, "keys": keys}

    def _compute_bayesian_evidence(self, vec_a: dict, vec_b: dict) -> dict:
        from .analysis import calculate_bayesian_evidence
        res = calculate_bayesian_evidence(vec_a, vec_b)
        # [BUGFIX] calculate_bayesian_evidence возвращает posteriors/likelihoods/priors как вложенные словари
        # Используем posteriors как итоговые вероятности после байесовского обновления
        posteriors = res.get("posteriors", {})
        return {
            "H0": float(posteriors.get("H0", 0.95)),
            "H1": float(posteriors.get("H1", 0.0)),
            "H2": float(posteriors.get("H2", 0.05)),
        }

    def suspicious_windows(self) -> list[dict]:
        """
        [ITER-1.4] Возвращает подозрительные интервалы/окна аномалий на основе матриц H0/H1/H2.
        """
        anomalies = []
        keys = list(self.vectors.keys())
        matrices = self.compute_n_x_n_matrix()
        matrix_h0 = matrices["H0"]
        matrix_h1 = matrices["H1"]
        matrix_h2 = matrices["H2"]
        
        # Нахождение сильных просадок H0 (высокая вероятность подмены/аномалии)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                score_h0 = matrix_h0[i][j]
                score_h1 = matrix_h1[i][j]
                score_h2 = matrix_h2[i][j]
                if not np.isnan(score_h0) and score_h0 < 0.4:
                    anomalies.append({
                        "photo_a_id": keys[i],
                        "photo_b_id": keys[j],
                        "score_h0": float(score_h0),
                        "score_h1": float(score_h1),
                        "score_h2": float(score_h2),
                        "metric_key": "cranial_face_index",
                        "reason": "Sudden geometric drop"
                    })
        return anomalies
