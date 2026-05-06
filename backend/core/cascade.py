def aggregate_texture_flags(tex_a: dict, tex_b: dict, conf_a: float, conf_b: float) -> float:
    """
    Симметричная агрегация текстурных аномалий (Силикон, Ретушь).
    Избавляемся от токсичного max().
    """
    silicone_a = tex_a.get('silicone_probability', 0.0)
    if silicone_a is None:
        silicone_a = 0.0
    silicone_b = tex_b.get('silicone_probability', 0.0)
    if silicone_b is None:
        silicone_b = 0.0
    
    # Взвешенное среднее по уровню доверия к маске кожи (Reliability)
    # Плохой кадр будет иметь низкий conf и не испортит статистику
    total_conf = conf_a + conf_b
    if total_conf < 1e-5:
        return 0.0
        
    weighted_silicone = (silicone_a * conf_a + silicone_b * conf_b) / total_conf
    return float(weighted_silicone)
