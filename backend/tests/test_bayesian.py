import pytest
import math
from core.verdict import BayesianForensicEngine
from core.analysis import _compute_texture_h1_evidence

def test_bayesian_likelihoods_same_person():
    """Тест: Маленькая дельта костей должна давать высокий likelihood для H0 (Один человек)"""
    engine = BayesianForensicEngine()
    likelihoods = engine.compute_likelihoods(
        metric_delta=0.01,  # Минимальное геометрическое расхождение
        base_sigma=0.04,
        delta_years=1,
        reliability=0.9,
        texture_h1_likelihood=0.01 # Нет признаков маски
    )
    
    # likelihoods = [L(E|H0), L(E|H1), L(E|H2)]
    l_h0, l_h1, l_h2 = likelihoods
    
    # Проверяем свойство модели: при малой дельте H0 > H2
    assert l_h0 > l_h2, "Likelihood H0 должен быть выше H2 при минимальных расхождениях"
    # H1 должен быть низким при отсутствии текстурных аномалий (texture_h1_likelihood=0.01)
    assert l_h1 < l_h0, "Likelihood H1 должен быть ниже H0 при отсутствии текстурных аномалий"

def test_epoch_texture_adjustments():
    """Тест: Старые аналоговые фото (до 2005) получают эпохальную корректировку шума"""
    tex_a = {
        "texture_silicone_prob": 0.5,
        "glcm_contrast": 0.6,
        "texture_pore_density": 20.0
    }
    tex_b = tex_a.copy()
    
    # 1. Тест старой эпохи (должна быть высокая толерантность к артефактам)
    old_result = _compute_texture_h1_evidence(tex_a, tex_b, year_a=1999, year_b=2000)
    
    # 2. Тест современной эпохи (строгая проверка)
    new_result = _compute_texture_h1_evidence(tex_a, tex_b, year_a=2024, year_b=2025)
    
    # Для старых фото порог синтетики должен быть искусственно завышен (threshold boost), 
    # чтобы шум сканирования не триггерил ложный H1 (дипфейк)
    assert old_result["threshold"] > new_result["threshold"], "Порог детекции масок для старых фото должен быть выше"
