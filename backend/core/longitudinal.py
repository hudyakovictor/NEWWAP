import numpy as np

class LongitudinalModel:
    def __init__(self, alpha=0.3):
        self.alpha = alpha  # Фактор сглаживания EMA (Экспоненциальное скользящее среднее)

    def compute_prediction_interval(self, historical_metrics: list, new_metric: float, population_sigma: float):
        """
        Оценивает аномальность нового измерения относительно истории человека.
        Использует Интервал Предсказания, который никогда не сужается до нуля.
        """
        n = len(historical_metrics)
        if n < 3:
            return 0.0 # Недостаточно данных для лонгитюдного вывода
            
        # 1. Защита от линейной деградации (Используем EMA)
        ema = historical_metrics[0]
        for val in historical_metrics[1:]:
            ema = self.alpha * val + (1 - self.alpha) * ema
            
        # 2. Оценка индивидуальной дисперсии
        individual_variance = np.var(historical_metrics, ddof=1)
        
        # 3. Истинный Интервал Предсказания (Prediction Interval)
        # Коридор нормы расширяется при неопределенности, а не сжимается!
        prediction_sigma = np.sqrt(individual_variance + (population_sigma**2 / n))
        
        # 4. Расчет Z-score
        z_score = np.abs(new_metric - ema) / prediction_sigma
        return float(z_score)

    def analyze_person_timeline(self, person_photos_metrics: list, target_metric: str, population_sigma: float = 0.05):
        """
        Прогоняет всю хронологию через модель старения.
        person_photos_metrics - список словарей, отсортированный по дате.
        """
        history = []
        anomalies = []
        
        for i, photo in enumerate(person_photos_metrics):
            val = photo.get(target_metric)
            if val is None:
                continue
                
            if len(history) >= 3:
                z_score = self.compute_prediction_interval(history, val, population_sigma)
                if z_score > 3.0:
                    anomalies.append({
                        "photo_id": photo["photo_id"],
                        "metric": target_metric,
                        "z_score": z_score,
                        "is_critical": True
                    })
            
            history.append(val)
            
        return anomalies
