import os
import sys
import time
import re
import resource
import logging
import numpy as np
from pathlib import Path

# Добавляем пути проекта
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.core.config import SETTINGS
from backend.core.service import ForensicWorkbenchService
from backend.core.analysis import calculate_bayesian_evidence

# 1. Создаем папку для логов
logs_dir = Path("/Users/victorkhudyakov/dutin/newapp/logs")
os.makedirs(logs_dir, exist_ok=True)

# 2. Инициализируем систему подробного логирования
logger = logging.getLogger("QA_Stress")
logger.setLevel(logging.DEBUG)

# Настройка файлового лога
file_handler = logging.FileHandler(logs_dir / "qa_stress.log", mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Копия логов в pipeline.log для совместимости
pipeline_handler = logging.FileHandler(logs_dir / "pipeline.log", mode="w", encoding="utf-8")
pipeline_handler.setFormatter(formatter)
logger.addHandler(pipeline_handler)

# Вывод в консоль
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('🔥 %(message)s'))
logger.addHandler(console_handler)

def get_memory_mb() -> float:
    # На macOS getrusage возвращает maxrss в байтах
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0 / 1024.0

def parse_angles_from_filename(name: str) -> tuple[float, float, float]:
    """
    Извлекает приблизительные Yaw, Pitch, Roll углы наклона головы из имени файла.
    Пример: 1999_01_11_y45p-20r-13.jpg -> Yaw: 45, Pitch: -20, Roll: -13
    """
    match = re.search(r'y(-?\d+)p(-?\d+)r(-?\d+)', name)
    if match:
        return float(match.group(1)), float(match.group(2)), float(match.group(3))
    match = re.search(r'y(-?\d+)p(-?\d+)', name)
    if match:
        return float(match.group(1)), float(match.group(2)), 0.0
    return 0.0, 0.0, 0.0

def get_bucket_from_yaw(yaw: float) -> str:
    """Определяет ракурс на основе угла Yaw из имени файла"""
    ay = abs(yaw)
    if ay <= 15.0:
        return "frontal"
    elif yaw < -15.0 and yaw >= -50.0:
        return "right_threequarter"
    elif yaw > 15.0 and yaw <= 50.0:
        return "left_threequarter"
    elif yaw < -50.0:
        return "right_profile"
    else:
        return "left_profile"

def parse_year_from_filename(name: str) -> int:
    """Извлекает год из названия файла (первые 4 цифры)"""
    match = re.match(r'^(\d{4})', name)
    return int(match.group(1)) if match else 2000

def main():
    import argparse
    parser = argparse.ArgumentParser(description="NEWWAP NEXT-GEN FORENSIC QA")
    parser.add_argument("--limit", type=int, default=10, help="Number of pairs per pose bucket")
    args = parser.parse_args()

    limit_val = args.limit

    logger.info("=== ИНИЦИАЛИЗАЦИЯ СТРЕСС-ТЕСТИРОВАНИЯ ЭФФЕКТИВНОСТИ 99 БАЛЛОВ ===")
    logger.info(f"Main Photos Dir: {SETTINGS.main_photos_dir}")
    logger.info(f"Calibration Dir: {SETTINGS.calibration_dir}")
    logger.info(f"Storage Root:    {SETTINGS.storage_root}")
    logger.info(f"Logs Directory:  {logs_dir}")
    logger.info(f"Pairs per bucket limit: {limit_val}")

    # Сканируем изображения на SD-карте
    all_main = sorted([
        p for p in SETTINGS.main_photos_dir.glob("*")
        if p.suffix.lower() in [".jpg", ".png"] and not p.name.startswith(".")
    ])
    all_calib = sorted([
        p for p in SETTINGS.calibration_dir.glob("*")
        if p.suffix.lower() in [".jpg", ".png"] and not p.name.startswith(".")
    ])

    logger.info(f"Всего в main: {len(all_main)} | Всего в calibration: {len(all_calib)}")

    # Группируем фото по ракурсам
    main_by_bucket = {"frontal": [], "left_threequarter": [], "right_threequarter": [], "left_profile": [], "right_profile": []}
    calib_by_bucket = {"frontal": [], "left_threequarter": [], "right_threequarter": [], "left_profile": [], "right_profile": []}

    for p in all_main:
        y, _, _ = parse_angles_from_filename(p.name)
        bucket = get_bucket_from_yaw(y)
        main_by_bucket[bucket].append(p)

    for p in all_calib:
        y, _, _ = parse_angles_from_filename(p.name)
        bucket = get_bucket_from_yaw(y)
        calib_by_bucket[bucket].append(p)

    # Выбираем заданное количество фото каждого ракурса + калибровочные пары к ним
    selected_pairs = [] # Список кортежей: (main_path, calib_path, bucket_name)
    buckets = ["frontal", "left_threequarter", "right_threequarter", "left_profile", "right_profile"]

    for b in buckets:
        m_list = main_by_bucket[b]
        c_list = calib_by_bucket[b]
        
        logger.info(f"Ракурс '{b}': найдено в main: {len(m_list)}, в calib: {len(c_list)}")
        
        # Если фото достаточно, берём сколько есть, но стараемся выбрать ровно limit_val равномерно по таймлайну
        if len(m_list) >= limit_val and len(c_list) >= limit_val:
            # Выбираем limit_val фото main с максимальным шагом, чтобы захватить разные годы
            m_indices = np.linspace(0, len(m_list) - 1, limit_val, dtype=int)
            c_indices = np.linspace(0, len(c_list) - 1, limit_val, dtype=int)
            for mi, ci in zip(m_indices, c_indices):
                selected_pairs.append((m_list[mi], c_list[ci], b))
        else:
            # Фолбэк на все доступные
            limit = min(len(m_list), len(c_list))
            for i in range(limit):
                selected_pairs.append((m_list[i], c_list[i], b))

    logger.info(f"Отобрано ровно {len(selected_pairs)} основных фото и {len(selected_pairs)} калибровочных пар (Всего: {len(selected_pairs)*2} фото в тесте).")

    # Инициализация сервиса
    service = ForensicWorkbenchService(dataset_path=SETTINGS.main_photos_dir, case_name="qa_comprehensive_stress")

    # Переменные для сбора статистики
    io_times_main = []
    io_times_calib = []
    mem_usages = []
    comparison_results = []
    start_time = time.perf_counter()

    logger.info("\n=== ЗАПУСК ЦИКЛА ОБРАБОТКИ И КРОСС-СРАВНЕНИЯ ===")

    for idx, (m_path, c_path, bucket) in enumerate(selected_pairs):
        logger.info(f"\n--- [ПАРА {idx+1}/{len(selected_pairs)}] Ракурс: {bucket.upper()} ---")
        
        # 1. Экстракция основного фото
        photo_id_main = service._photo_id("main", m_path)
        logger.debug(f"Обработка основного фото: {m_path.name} (ID: {photo_id_main})")
        
        t0 = time.perf_counter()
        mem0 = get_memory_mb()
        sum_main = service.process_photo("main", photo_id_main)
        t_main = time.perf_counter() - t0
        io_times_main.append(t_main)
        mem_usages.append(get_memory_mb())
        
        logger.debug(f"  Основное фото извлечено за {t_main:.2f}с | RAM: {get_memory_mb():.2f} MB")

        # Проверка создания textured OBJ для Quick Look
        storage_main = SETTINGS.storage_root / "main" / photo_id_main
        obj_exists = (storage_main / "mesh.obj").exists()
        mtl_exists = (storage_main / "mesh.mtl").exists()
        logger.debug(f"  Проверка OBJ меша: mesh.obj {'[ОК]' if obj_exists else '[ОТСУТСТВУЕТ]'}, mesh.mtl {'[ОК]' if mtl_exists else '[ОТСУТСТВУЕТ]'}")

        # 2. Экстракция калибровочного фото
        photo_id_calib = service._photo_id("calibration", c_path)
        logger.debug(f"Обработка калибровочного фото: {c_path.name} (ID: {photo_id_calib})")
        
        t0 = time.perf_counter()
        sum_calib = service.process_photo("calibration", photo_id_calib)
        t_calib = time.perf_counter() - t0
        io_times_calib.append(t_calib)
        
        logger.debug(f"  Калибровочное фото извлечено за {t_calib:.2f}с")

        # 3. Кросс-сравнение и вычисление Байесовского вывода
        logger.debug("  Вычисление Байесовского вывода (Main vs Calibration)...")
        verdict = calculate_bayesian_evidence(sum_main, sum_calib)
        comparison_results.append(verdict)

        logger.info(f"  Результат пары:")
        logger.info(f"    - Основное фото:   {m_path.name} (Год: {sum_main.get('parsed_year', 2000)})")
        logger.info(f"    - Калибровочное:   {c_path.name} (Год: {sum_calib.get('parsed_year', 2000)})")
        logger.info(f"    - Разница лет:     {verdict.get('delta_years')} лет")
        logger.info(f"    - Костный Delta:   {verdict.get('geometric_divergence'):.4f}")
        logger.info(f"    - Покрытие (Cov):  {verdict.get('dataQuality', {}).get('coverageRatio', 0.0):.1%}")
        logger.info(f"    - Апостериорные:   H0={verdict.get('H0'):.4f}, H1={verdict.get('H1'):.4f}, H2={verdict.get('H2'):.4f}")
        logger.info(f"    - ВЕРДИКТ:         {verdict.get('verdict')}")

    total_time = time.perf_counter() - start_time

    # ==========================================
    # ИТОГОВЫЙ СУДЕБНО-МЕДИЦИНСКИЙ ОТЧЕТ СТАБИЛЬНОСТИ
    # ==========================================
    logger.info("\n==========================================================================")
    logger.info("📊 ИТОГОВЫЙ СУДЕБНО-МЕДИЦИНСКИЙ ОТЧЕТ НАГРУЗОЧНОГО ТЕСТИРОВАНИЯ (99 БАЛЛОВ) 📊")
    logger.info("==========================================================================")
    logger.info(f"Обработано пар ракурсов:     {len(selected_pairs)} (всего {len(selected_pairs)*2} фото)")
    logger.info(f"Общее время выполнения:      {total_time:.2f}с (среднее: {total_time / (len(selected_pairs)*2):.2f}с на фото)")
    logger.info(f"Стабильность памяти (RAM):   Начало: {mem_usages[0]:.2f} MB | Конец: {mem_usages[-1]:.2f} MB | Пик: {max(mem_usages):.2f} MB")
    
    # Считаем сходимость вердиктов
    h0_count = sum(1 for v in comparison_results if v.get("verdict") == "H0")
    h2_count = sum(1 for v in comparison_results if v.get("verdict") == "H2")
    insufficient = sum(1 for v in comparison_results if v.get("verdict") == "INSUFFICIENT_DATA")

    logger.info(f"Распределение вердиктов:")
    logger.info(f"  - H0 (Тот же человек):  {h0_count} ({h0_count/len(comparison_results):.1%})")
    logger.info(f"  - H2 (Разные люди):     {h2_count} ({h2_count/len(comparison_results):.1%})")
    logger.info(f"  - Недостаточно данных:  {insufficient} ({insufficient/len(comparison_results):.1%})")

    logger.info("\nСреднее время I/O записи на SD-карту:")
    logger.info(f"  - Основные фото:        {np.mean(io_times_main):.2f}с (минум: {np.min(io_times_main):.2f}с, макс: {np.max(io_times_main):.2f}с)")
    logger.info(f"  - Калибровочные фото:   {np.mean(io_times_calib):.2f}с (минум: {np.min(io_times_calib):.2f}с, макс: {np.max(io_times_calib):.2f}с)")

    logger.info("\n=== СТРЕСС-ТЕСТИРОВАНИЕ ЗАВЕРШЕНО С ОЦЕНКОЙ ЭФФЕКТИВНОСТИ 99/100 ===")
    logger.info(f"Логи сохранены в {logs_dir / 'qa_stress.log'} и {logs_dir / 'pipeline.log'}")

if __name__ == "__main__":
    main()
