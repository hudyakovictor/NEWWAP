"""
Longitudinal (временной) анализ для forensic-расследований.

[FIX-28, FIX-30, FIX-31, FIX-36] Модуль для анализа изменений лица во времени,
а не только pairwise сравнений.

Строит временную линию фото, анализирует тренды и детектирует аномалии.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
import math


@dataclass
class TimelinePoint:
    """Точка на временной линии."""
    photo_id: str
    timestamp: datetime
    year: int
    metrics: dict[str, float]
    quality_score: float
    pose_reliability: float
    bucket: str


@dataclass
class TrendAnalysis:
    """Анализ тренда для одной метрики."""
    metric_key: str
    slope: float  # Наклон (изменение в год)
    intercept: float
    r_squared: float  # Качество fit
    expected_range: tuple[float, float]  # Ожидаемый диапазон для возраста
    anomaly_score: float  # 0 = норма, >1 = аномалия


@dataclass
class ChronologicalAnomaly:
    """Хронологическая аномалия."""
    photo_id: str
    year: int
    metric_key: str
    observed_value: float
    expected_value: float
    deviation_sigma: float  # Отклонение в сигмах
    severity: str  # "info", "warn", "danger"
    explanation: str


class LongitudinalAnalyzer:
    """
    [FIX-30] Longitudinal анализ для построения временной линии изменений.
    
    Вместо только pairwise сравнений строит полную временную модель:
    - Тренды изменения метрик с возрастом
    - Ожидаемые диапазоны для каждого возраста
    - Аномалии, выходящие за пределы нормы
    """
    
    # Ожидаемые тренды изменения анатомических метрик с возрастом
    # (в единицах метрики в год)
    AGE_TRENDS = {
        # Костные метрики — стабильны (мало меняются с возрастом)
        "nose_projection_ratio": {"slope": 0.0, "variability": 0.02},
        "orbit_depth_L_ratio": {"slope": 0.0, "variability": 0.02},
        "orbit_depth_R_ratio": {"slope": 0.0, "variability": 0.02},
        "jaw_width_ratio": {"slope": 0.005, "variability": 0.03},  # Челюсть растет до 25
        "cranial_face_index": {"slope": 0.0, "variability": 0.015},
        "interorbital_ratio": {"slope": 0.0, "variability": 0.02},
        
        # Мягкие ткани — меняются с возрастом
        "chin_projection_ratio": {"slope": -0.01, "variability": 0.03},  # Утрата объема
        "gonial_angle_L": {"slope": 0.0, "variability": 0.025},
        "gonial_angle_R": {"slope": 0.0, "variability": 0.025},
        "canthal_tilt_L": {"slope": -0.008, "variability": 0.02},  # Угол опускается
        "canthal_tilt_R": {"slope": -0.008, "variability": 0.02},
        
        # Текстурные признаки — сильно меняются
        "texture_wrinkle_forehead": {"slope": 0.015, "variability": 0.05},  # Морщины растут
        "texture_wrinkle_nasolabial": {"slope": 0.012, "variability": 0.04},
        "texture_pore_density": {"slope": -0.3, "variability": 1.0},  # Поры размываются
        "texture_global_smoothness": {"slope": -0.01, "variability": 0.03},  # Кожа грубеет
    }
    
    def __init__(self, min_observations: int = 3):
        self.min_observations = min_observations
        self.timeline: list[TimelinePoint] = []
        self.trends: dict[str, TrendAnalysis] = {}
        self.anomalies: list[ChronologicalAnomaly] = []
    
    def add_photo(self, summary: dict[str, Any]) -> None:
        """Добавить фото в временную линию."""
        # [FIX-28] Используем строгий канонический временной индекс
        photo_id = summary.get("photo_id", "unknown")
        
        # Парсим дату из summary
        year = summary.get("year", summary.get("parsed_year"))
        if year is None:
            # Пытаемся извлечь из photo_id или filename
            year = self._extract_year_from_id(photo_id)
        
        if year is None:
            raise ValueError(f"Cannot determine year for photo {photo_id}")
        
        # Создаем timestamp (1 января для простоты, можно улучшить)
        timestamp = datetime(year, 1, 1)
        
        # Получаем метрики
        metrics = summary.get("metrics", {})
        
        # Фильтруем только числовые метрики
        numeric_metrics = {
            k: float(v) for k, v in metrics.items()
            if isinstance(v, (int, float)) and not math.isnan(v)
        }
        
        # Quality и reliability
        quality = summary.get("quality", {})
        quality_score = quality.get("overall_score", 0.5) if isinstance(quality, dict) else 0.5
        
        status_detail = summary.get("status_detail", {})
        reliability_tier = status_detail.get("reliability_tier", "medium")
        pose_reliability = {"high": 0.9, "medium": 0.7, "low": 0.5}.get(reliability_tier, 0.7)
        
        bucket = summary.get("bucket", "unclassified")
        
        point = TimelinePoint(
            photo_id=photo_id,
            timestamp=timestamp,
            year=year,
            metrics=numeric_metrics,
            quality_score=quality_score,
            pose_reliability=pose_reliability,
            bucket=bucket,
        )
        
        self.timeline.append(point)
        # Сортируем по времени
        self.timeline.sort(key=lambda p: p.timestamp)
    
    def _extract_year_from_id(self, photo_id: str) -> int | None:
        """Извлечь год из photo_id (формат: prefix-YYYY-... или YYYY-...)."""
        import re
        # Ищем 4 цифры подряд
        match = re.search(r'(\d{4})', photo_id)
        if match:
            year = int(match.group(1))
            if 1950 <= year <= 2030:  # Разумный диапазон
                return year
        return None
    
    def analyze_trends(self) -> dict[str, TrendAnalysis]:
        """
        [FIX-30] Анализ трендов изменения метрик с возрастом.
        
        Использует linear regression для оценки наклона изменения.
        """
        if len(self.timeline) < self.min_observations:
            return {}
        
        trends = {}
        
        # Для каждой метрики с известным трендом
        for metric_key, expected in self.AGE_TRENDS.items():
            # Собираем наблюдения
            observations = []
            years = []
            
            for point in self.timeline:
                if metric_key in point.metrics:
                    # Взвешиваем по качеству и надежности
                    weight = point.quality_score * point.pose_reliability
                    if weight > 0.5:  # Только достаточно надежные
                        observations.append(point.metrics[metric_key])
                        years.append(point.year)
            
            if len(observations) < self.min_observations:
                continue
            
            # Simple linear regression
            n = len(observations)
            x_mean = sum(years) / n
            y_mean = sum(observations) / n
            
            # Вычисляем slope и intercept
            numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(years, observations))
            denominator = sum((x - x_mean) ** 2 for x in years)
            
            if denominator > 0:
                slope = numerator / denominator
            else:
                slope = 0
            
            intercept = y_mean - slope * x_mean
            
            # R-squared
            ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(years, observations))
            ss_tot = sum((y - y_mean) ** 2 for y in observations)
            r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0
            
            # Ожидаемый диапазон для последнего года
            last_year = max(years)
            expected_value = intercept + slope * last_year

            # ИСПРАВЛЕНИЕ: Стандартная ошибка сужается при росте N
            if n <= 0:
                expected_variability = expected["variability"]
            else:
                # Базовая вариативность делится на корень из размера выборки
                expected_variability = expected["variability"] / math.sqrt(n)

            # Ограничиваем минимально допустимый разброс, чтобы избежать деления на 0
            # при проверке аномалий на больших датасетах
            expected_variability = max(expected_variability, 0.005)

            expected_range = (
                expected_value - 2 * expected_variability,
                expected_value + 2 * expected_variability,
            )
            
            # Аномалия: насколько фактический slope отличается от ожидаемого
            expected_slope = expected["slope"]
            slope_deviation = abs(slope - expected_slope) / (expected["variability"] + 0.001)
            
            trends[metric_key] = TrendAnalysis(
                metric_key=metric_key,
                slope=slope,
                intercept=intercept,
                r_squared=r_squared,
                expected_range=expected_range,
                anomaly_score=slope_deviation,
            )
        
        self.trends = trends
        return trends
    
    def detect_anomalies(self) -> list[ChronologicalAnomaly]:
        """
        [FIX-31] Детекция хронологических аномалий.
        
        Сравнивает наблюдаемые значения с ожидаемыми от тренда.
        """
        if not self.trends:
            self.analyze_trends()
        
        anomalies = []
        
        for point in self.timeline:
            for metric_key, trend in self.trends.items():
                if metric_key not in point.metrics:
                    continue
                
                observed = point.metrics[metric_key]
                expected = trend.intercept + trend.slope * point.year
                
                # Отклонение в сигмах
                expected_std = (trend.expected_range[1] - trend.expected_range[0]) / 4
                if expected_std > 0:
                    deviation_sigma = abs(observed - expected) / expected_std
                else:
                    deviation_sigma = 0
                
                # Определяем severity
                if deviation_sigma > 3:
                    severity = "danger"
                elif deviation_sigma > 2:
                    severity = "warn"
                elif deviation_sigma > 1.5:
                    severity = "info"
                else:
                    continue  # Не аномалия
                
                # Пояснение
                if deviation_sigma > 2:
                    if observed > expected:
                        explanation = f"{metric_key} выше ожидаемого на {deviation_sigma:.1f}σ"
                    else:
                        explanation = f"{metric_key} ниже ожидаемого на {deviation_sigma:.1f}σ"
                else:
                    explanation = f"{metric_key} в пределах нормы"
                
                anomalies.append(ChronologicalAnomaly(
                    photo_id=point.photo_id,
                    year=point.year,
                    metric_key=metric_key,
                    observed_value=observed,
                    expected_value=expected,
                    deviation_sigma=deviation_sigma,
                    severity=severity,
                    explanation=explanation,
                ))
        
        # Сортируем по severity
        severity_order = {"danger": 0, "warn": 1, "info": 2}
        anomalies.sort(key=lambda a: severity_order.get(a.severity, 3))
        
        self.anomalies = anomalies
        return anomalies
    
    def compute_chronological_likelihood(self, photo_a_id: str, photo_b_id: str) -> dict[str, Any]:
        """
        [FIX-36] Вычисляет хронологическое правдоподобие для пары фото.
        
        Учитывает, согласуются ли изменения между двумя точками с ожидаемыми трендами.
        """
        # Находим точки
        point_a = next((p for p in self.timeline if p.photo_id == photo_a_id), None)
        point_b = next((p for p in self.timeline if p.photo_id == photo_b_id), None)
        
        if not point_a or not point_b:
            return {
                "likelihood": 0.5,
                "consistent": False,
                "note": "One or both photos not in timeline",
            }
        
        year_delta = abs(point_a.year - point_b.year)
        
        if year_delta == 0:
            # Одновременные фото — должны быть очень похожи
            return {
                "likelihood": 1.0,
                "consistent": True,
                "note": "Same year — expecting high similarity",
            }
        
        # Проверяем, согласуются ли изменения с трендами
        inconsistencies = []
        total_metrics = 0
        
        for metric_key in set(point_a.metrics.keys()) & set(point_b.metrics.keys()):
            if metric_key not in self.AGE_TRENDS:
                continue
            
            total_metrics += 1
            
            val_a = point_a.metrics[metric_key]
            val_b = point_b.metrics[metric_key]
            actual_change = (val_b - val_a) / year_delta  # Изменение в год
            
            expected = self.AGE_TRENDS[metric_key]
            expected_change = expected["slope"]
            tolerance = expected["variability"] * 2  # 2 sigma
            
            if abs(actual_change - expected_change) > tolerance:
                inconsistencies.append({
                    "metric": metric_key,
                    "actual_change_per_year": actual_change,
                    "expected_change_per_year": expected_change,
                    "deviation": abs(actual_change - expected_change),
                })
        
        # Likelihood на основе согласованности
        if total_metrics == 0:
            likelihood = 0.5
        else:
            consistency_ratio = 1 - (len(inconsistencies) / total_metrics)
            likelihood = max(0.1, min(0.95, consistency_ratio))
        
        return {
            "likelihood": likelihood,
            "consistent": len(inconsistencies) == 0,
            "year_delta": year_delta,
            "inconsistencies": inconsistencies,
            "total_metrics_checked": total_metrics,
        }
    
    def get_summary(self) -> dict[str, Any]:
        """Возвращает сводку longitudinal анализа."""
        return {
            "timeline_length": len(self.timeline),
            "year_range": {
                "start": min(p.year for p in self.timeline) if self.timeline else None,
                "end": max(p.year for p in self.timeline) if self.timeline else None,
            },
            "trends_analyzed": len(self.trends),
            "anomalies_detected": len(self.anomalies),
            "anomaly_breakdown": {
                "danger": sum(1 for a in self.anomalies if a.severity == "danger"),
                "warn": sum(1 for a in self.anomalies if a.severity == "warn"),
                "info": sum(1 for a in self.anomalies if a.severity == "info"),
            },
        }


def build_longitudinal_model(summaries: list[dict[str, Any]]) -> LongitudinalAnalyzer:
    """
    [FIX-30] Строит longitudinal модель из списка summary.
    
    Usage:
        model = build_longitudinal_model(summaries)
        trends = model.analyze_trends()
        anomalies = model.detect_anomalies()
        chron_lh = model.compute_chronological_likelihood("id_a", "id_b")
    """
    analyzer = LongitudinalAnalyzer()
    
    for summary in summaries:
        try:
            analyzer.add_photo(summary)
        except ValueError as e:
            # Логируем, но продолжаем с другими фото
            print(f"Warning: {e}")
    
    if len(analyzer.timeline) >= 3:
        analyzer.analyze_trends()
        analyzer.detect_anomalies()
    
    return analyzer
