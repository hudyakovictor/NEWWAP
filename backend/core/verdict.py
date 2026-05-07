import numpy as np
from core.constants import PRIOR_SAME_PERSON, PRIOR_IDENTITY_SWAP

class BayesianForensicEngine:
    def __init__(self, base_prior_h0=None, base_prior_h1=None, base_prior_h2=None):
        # Априорные вероятности (Prior) НЕ зависят от времени между фото!
        # H0: Тот же человек, H1: Модификация (Дипфейк/Маска), H2: Разные люди
        # [BUGFIX] Унифицированы с BayesianMultiHypothesisEngine (core/constants.py)
        if base_prior_h0 is None:
            base_prior_h0 = PRIOR_SAME_PERSON
        if base_prior_h1 is None:
            base_prior_h1 = PRIOR_IDENTITY_SWAP
        if base_prior_h2 is None:
            base_prior_h2 = 1.0 - PRIOR_SAME_PERSON - PRIOR_IDENTITY_SWAP
        self.priors = np.array([base_prior_h0, base_prior_h1, base_prior_h2])
        
    def compute_likelihoods(self, metric_delta: float, base_sigma: float, delta_years: float, reliability: float, texture_h1_likelihood: float = 1e-6):
        """
        Вычисляет Правдоподобие (Likelihood) наблюдения с учетом прошедшего времени.
        Исправлена философская ошибка Байеса (B-01).
        
        [BUGFIX] H1 likelihood теперь вычисляется из текстурных данных,
        а не захардкожен как 1e-6. Без этого система принципиально не могла
        детектировать подмену личности (маски, дипфейки).
        """
        # 1. Расширение дисперсии от времени (Time-based Variance Expansion)
        # Допускаем биологический дрейф: +1% к базовому шуму за каждый год
        age_drift_factor = 1.0 + (0.01 * delta_years)
        effective_sigma = base_sigma * age_drift_factor
        
        # 2. Истинный Сигнал/Шум (SNR)
        # БАГФИКС: Мы больше не умножаем delta на reliability!
        # Мы расширяем неопределенность (sigma) при плохой надежности.
        adjusted_sigma = effective_sigma / max(reliability, 0.1)
        
        # 3. Расчет плотностей вероятностей (PDF)
        # Likelihood для H0 (Тот же человек): Гауссиана вокруг 0
        l_h0 = self._gaussian_pdf(metric_delta, mean=0.0, sigma=adjusted_sigma)
        
        # [BUGFIX] H1 (подмена/маска/дипфейк): берём из текстурного анализа
        # Если текстурное доказательство не передано — используем минимальный baseline
        l_h1 = max(float(texture_h1_likelihood), 1e-6)
        
        # Likelihood для H2 (Разные люди): Равномерное или широкое распределение
        # Базируется на популяционной дисперсии (population_sigma)
        population_sigma = base_sigma * 15.0 # Разные люди отличаются сильно
        l_h2 = self._gaussian_pdf(metric_delta, mean=0.0, sigma=population_sigma)
        
        return np.array([l_h0, l_h1, l_h2])
    
    def _gaussian_pdf(self, x, mean, sigma):
        return (1.0 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mean) / sigma) ** 2)
