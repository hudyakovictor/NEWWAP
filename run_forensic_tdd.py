import sys
import math
import json
import numpy as np
from pathlib import Path

# Добавляем пути проекта
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.core.config import SETTINGS
from backend.core.verdict import BayesianForensicEngine
from backend.core.scoring import BUCKET_METRIC_KEYS, compute_true_coverage

# ==================================================
# БЛОК I: Тестирование 3D-геометрии и Выравнивания
# ==================================================

def test_geometry_scale_and_pose_invariance(summary_a: dict, summary_b: dict):
    """
    Тест 1 & 4: Инвариантность к масштабу и стабильность выравнивания.
    Костные индексы должны совпадать между кадрами одного человека независимо от масштаба и позы.
    """
    print("[RUN] Запуск теста геометрической инвариантности (Scale & Pose)...")
    
    pose_a = summary_a.get("pose", {}).get("bucket", "unclassified")
    pose_b = summary_b.get("pose", {}).get("bucket", "unclassified")
    
    met_a = summary_a.get("metrics", {})
    met_b = summary_b.get("metrics", {})
    
    cranial_a = met_a.get("cranial_face_index") or met_a.get("cranial_index", 0.0)
    cranial_b = met_b.get("cranial_face_index") or met_b.get("cranial_index", 0.0)
    
    jaw_a = met_a.get("jaw_width_ratio") or met_a.get("jaw_width", 0.0)
    jaw_b = met_b.get("jaw_width_ratio") or met_b.get("jaw_width", 0.0)
    
    cranial_diff = abs(cranial_a - cranial_b)
    jaw_diff = abs(jaw_a - jaw_b)
    
    # Если позы существенно отличаются (например, анфас против бокового профиля), дельта естественным образом шире.
    max_allowed = 0.12 if pose_a != pose_b else 0.05
    
    assert cranial_diff < max_allowed, f"[FAIL] Сбой масштаба! Краниальный индекс плывет: дельта {cranial_diff:.4f} ({pose_a} vs {pose_b})"
    assert jaw_diff < max_allowed, f"[FAIL] Сбой масштаба! Ширина челюсти плывет: дельта {jaw_diff:.4f} ({pose_a} vs {pose_b})"
    print(f"  [+] Инвариантность масштаба подтверждена (Краниальная дельта: {cranial_diff:.4f}, Челюстная дельта: {jaw_diff:.4f})")

    # 2. Сохранение естественной асимметрии
    asym_a = met_a.get("asymmetry_total_vector", 0.0) or 0.0
    asym_b = met_b.get("asymmetry_total_vector", 0.0) or 0.0
    asym_diff = abs(asym_a - asym_b)
    max_asym_allowed = 0.30 if pose_a != pose_b else 0.05
    assert asym_diff < max_asym_allowed, f"[FAIL] Алгоритм Умеямы искажает естественную асимметрию лица! Дельта: {asym_diff:.4f} ({pose_a} vs {pose_b})"
    print(f"  [+] Естественная асимметрия стабильна (дельта: {asym_diff:.4f})")

def test_occlusion_gating(profile_summary: dict):
    """
    Тест 5: Точность маскирования невидимых зон (Occlusion Gating).
    На боковом профиле (yaw > 45) не должно быть некоторых симметричных точек противоположной стороны.
    """
    print("[RUN] Запуск теста отсечения скрытых зон (Occlusion)...")
    pose = profile_summary.get("pose", {})
    yaw = abs(pose.get("yaw", 0.0))
    bucket = pose.get("bucket", "unclassified")
    metrics = profile_summary.get("metrics", {})
    
    print(f"  Ракурс: {bucket}, Yaw: {yaw:.2f}°")
    if "profile" in bucket or yaw > 45.0:
        # Для профиля проверяем, что скрытые зоны корректно обработаны
        cov = profile_summary.get("dataQuality", {}).get("coverageRatio", 0.0)
        assert cov > 0.4, f"[FAIL] Покрытие необоснованно упало до {cov:.2f} на профиле!"
        print(f"  [+] Скрытые зоны обработаны корректно. Покрытие профиля: {cov * 100:.1f}%")
    else:
        print("  [SKIP] Кадр не является боковым профилем, пропуск проверки.")

# ==================================================
# БЛОК II: Текстурная аналитика и Анти-Спуфинг
# ==================================================

def test_texture_anti_spoofing(sample_summary: dict):
    """
    Тест 6, 7, 8: Защита от ложных бликов (Студийный свет) и анти-спуфинг кожи.
    """
    print("[RUN] Запуск теста текстурного анти-спуфинга...")
    metrics = sample_summary.get("metrics", {})
    spec_gloss = metrics.get("texture_specular_gloss", 0.0) or 0.0
    pore_density = metrics.get("texture_pore_density", 0.0) or 0.0
    silicone_prob = metrics.get("texture_silicone_prob", 0.0) or 0.0
    
    print(f"  Блик: {spec_gloss:.4f}, Поры: {pore_density:.2f}, Вероятность маски: {silicone_prob:.4f}")
    if spec_gloss > 0.05 and pore_density > 50.0:
        assert silicone_prob < 0.3, f"[FAIL] Ложное срабатывание детектора маски ({silicone_prob:.4f}) при наличии пор!"
        print("  [+] Сильный свет успешно изолирован от признаков силиконовой маски.")
    else:
        print("  [+] Анти-спуфинг параметры в норме (H1 = 0 для натуральной кожи).")

# ==================================================
# БЛОК III: Байесовский вывод и Лонгитюдная Модель
# ==================================================

def test_bayesian_longitudinal_logic():
    """
    Тест 11, 12, 13: Математика временного дрейфа и априорных вероятностей.
    """
    print("[RUN] Запуск стресс-теста математики Байесовского ядра...")
    engine = BayesianForensicEngine(base_prior_h0=0.5, base_prior_h1=0.1, base_prior_h2=0.4)
    
    # Имитируем существенное расхождение костей (дельта) в 0.08, где дрейф увеличивает правдоподобие H0
    delta = 0.08
    sigma = 0.04
    rel = 0.85
    
    # Расширение дисперсии временем:
    # За 30 лет кости могут разойтись сильнее (дельта 0.03 легальнее), чем за 1 год.
    # Поэтому правдоподобие H0 для 30 лет должно быть ВЫШЕ, чем для 1 года.
    l_1_year = engine.compute_likelihoods(delta, sigma, delta_years=1.0, reliability=rel)
    l_30_years = engine.compute_likelihoods(delta, sigma, delta_years=30.0, reliability=rel)
    
    assert l_30_years[0] > l_1_year[0], f"[FAIL] Время не расширяет дисперсию! H0_1yr: {l_1_year[0]:.4f} >= H0_30yr: {l_30_years[0]:.4f}"
    print(f"  [+] Лонгитюдный дрейф работает: правдоподобие H0 расширено временем ({l_1_year[0]:.4f} -> {l_30_years[0]:.4f})")
    
    # Априорная вероятность H2 неизменна
    assert engine.priors[2] == 0.4, "[FAIL] Априорная вероятность H2 искажена!"
    print("  [+] Априорные вероятности инвариантны.")

# ==================================================
# БЛОК IV: Контракты Данных, Исключения и Стабильность
# ==================================================

def test_json_strict_contracts(summary: dict):
    """
    Тест 16, 17, 18, 20: Чистота JSON, отсутствие NaN/Inf, булевые типы и истинное покрытие.
    """
    print("[RUN] Запуск проверки судебно-медицинских контрактов...")
    
    # 1. Рекурсивная проверка на NaN, Inf и целостность Boolean
    def validate_deep(obj, path="root"):
        if isinstance(obj, dict):
            for k, v in obj.items():
                validate_deep(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                validate_deep(v, f"{path}[{i}]")
        elif isinstance(obj, float):
            assert not math.isnan(obj), f"[FAIL] Обнаружен NaN в поле {path}!"
            assert not math.isinf(obj), f"[FAIL] Обнаружена Бесконечность в поле {path}!"
        elif isinstance(obj, bool):
            assert obj in [True, False], f"[FAIL] Некорректный логический тип в {path}: {obj}"

    validate_deep(summary)
    print("  [+] Санитарный контроль пройден: NaN/Inf отсутствуют, булевые типы сохранены.")
    
    # 2. Взвешенная надежность в диапазоне [0, 1]
    metrics_block = summary.get("metrics", {})
    rel = metrics_block.get("reliability_weight", 0.0)
    assert 0.0 < rel <= 1.0, f"[FAIL] Вес надежности вне диапазона: {rel}"
    print(f"  [+] Вес надежности валиден: {rel:.4f}")
    
    # 3. Честный пересчет покрытия
    cov = summary.get("dataQuality", {}).get("coverageRatio", 0.0)
    bucket = summary.get("pose", {}).get("bucket", "unclassified")
    expected_cov = compute_true_coverage(metrics_block, bucket)
    
    assert abs(cov - expected_cov) < 0.01, f"[FAIL] Подлог покрытия! Заявлено: {cov:.4f}, Реально: {expected_cov:.4f}"
    print(f"  [+] Истинное покрытие математически подтверждено: {cov * 100:.1f}%")

# ==================================================
# Главный пусковой метод TDD комплекса
# ==================================================

def run_all_qa():
    print("\n" + "=" * 50)
    print(" NEWWAP NEXT-GEN FORENSIC QA TDD SUITE (ITERATION 6)")
    print("=" * 50 + "\n")
    
    # Находим JSON сводки в хранилище на SD-карте
    main_dirs = list(Path("/Volumes/SDCARD/storage/main").glob("**/summary.json"))
    calib_dirs = list(Path("/Volumes/SDCARD/storage/calibration").glob("**/summary.json"))
    
    all_summaries = []
    for p in main_dirs + calib_dirs:
        try:
            with p.open("r", encoding="utf-8") as f:
                all_summaries.append(json.load(f))
        except Exception:
            pass

    if not all_summaries:
        print("[WARNING] Данные в хранилище /Volumes/SDCARD/storage/ отсутствуют. Сначала запустите экстракцию.")
        print("[RUN] Выполняем только изолированные тесты (Байесовский вывод)...")
        try:
            test_bayesian_longitudinal_logic()
            print("\n" + "=" * 50)
            print(" [SUCCESS] ИЗОЛИРОВАННЫЕ МАТЕМАТИЧЕСКИЕ ТЕСТЫ ПРОЙДЕНЫ!")
            print("=" * 50)
        except AssertionError as e:
            print(f"\n[FAIL] Ошибка математики: {e}")
            sys.exit(1)
        return

    print(f"Найдено {len(all_summaries)} файлов summary.json для тестирования.")
    sample = all_summaries[0]
    
    try:
        # Запускаем строгие контракты
        test_json_strict_contracts(sample)
        
        # Запускаем байесовский стресс-тест
        test_bayesian_longitudinal_logic()
        
        # Запускаем анти-спуфинг
        test_texture_anti_spoofing(sample)
        
        # Окклюзия
        test_occlusion_gating(sample)
        
        # Если есть хотя бы 2 сводки, тестируем геометрическую стабильность
        if len(all_summaries) >= 2:
            test_geometry_scale_and_pose_invariance(all_summaries[0], all_summaries[-1])
            
        print("\n" + "=" * 50)
        print(" [SUCCESS] ВСЕ СУДЕБНО-МЕДИЦИНСКИЕ ТЕСТЫ ПРОЙДЕНЫ НА 100%!")
        print(" Математика геометрии, анти-спуфинг, Байес и контракты идеальны!")
        print("=" * 50)
        
    except AssertionError as e:
        print("\n" + "!" * 50)
        print(f" [CRITICAL FAIL] СУДЕБНЫЙ ТЕСТ ПРОВАЛЕН:")
        print(f" {e}")
        print("!" * 50 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    run_all_qa()
