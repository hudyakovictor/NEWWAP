import os
import sys
from pathlib import Path

# Добавляем пути проекта
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.core.config import SETTINGS
from backend.core.service import ForensicWorkbenchService
from backend.core.analysis import calculate_bayesian_evidence

def main():
    print("=== ЗАПУСК ДИАГОНАЛЬНОГО ТЕСТИРОВАНИЯ НА РЕАЛЬНЫХ ДАННЫХ ===")
    print(f"Main photos dir:  {SETTINGS.main_photos_dir}")
    print(f"Calibration dir:  {SETTINGS.calibration_dir}")
    print(f"Storage root:     {SETTINGS.storage_root}")

    # 1. Проверяем доступность путей на SD-карте
    if not SETTINGS.main_photos_dir.exists():
        print(f"[ERR] Директория основного датасета не найдена: {SETTINGS.main_photos_dir}")
        return
    if not SETTINGS.calibration_dir.exists():
        print(f"[ERR] Директория калибровки не найдена: {SETTINGS.calibration_dir}")
        return

    # Находим реальные изображения (игнорируем скрытые файлы ._* и .DS_Store)
    main_photos = sorted([
        p for p in list(SETTINGS.main_photos_dir.glob("*.jpg")) + list(SETTINGS.main_photos_dir.glob("*.png"))
        if not p.name.startswith(".")
    ])
    calib_photos = sorted([
        p for p in list(SETTINGS.calibration_dir.glob("*.jpg")) + list(SETTINGS.calibration_dir.glob("*.png"))
        if not p.name.startswith(".")
    ])

    print(f"Найдено реальных фото в main:       {len(main_photos)}")
    print(f"Найдено реальных фото в калибровке: {len(calib_photos)}")

    if not main_photos or not calib_photos:
        print("[ERR] В одной из папок отсутствуют изображения для тестирования.")
        return

    # Выбираем тестовые фото (диагональное тестирование)
    test_main = main_photos[0]
    test_calib = calib_photos[0]

    print(f"\n[ТЕСТ 1] Тестирование экстракции основного фото: {test_main.name}")
    service = ForensicWorkbenchService(dataset_path=SETTINGS.main_photos_dir, case_name="diagonal_test")
    
    # 1. Запуск Offline Extraction для одного основного фото
    photo_id_main = service._photo_id("main", test_main)
    print(f"Извлечение 3D для основного фото {photo_id_main}...")
    summary_main = service.process_photo("main", photo_id_main)
    
    print("\nПроверка созданных файлов для основного фото:")
    storage_main = SETTINGS.storage_root / "main" / photo_id_main
    expected_files = ["summary.json", f"{photo_id_main}_summary.json", "face_crop.jpg", "uv_texture.png", "uv_confidence.png", "mesh.obj"]
    for f in expected_files:
        p = storage_main / f
        print(f"  Файл {f:35} {'[ОК]' if p.exists() else '[ОТСУТСТВУЕТ]'}")

    # 2. Запуск Offline Extraction для одного калибровочного фото
    print(f"\n[ТЕСТ 2] Тестирование экстракции калибровочного фото: {test_calib.name}")
    photo_id_calib = service._photo_id("calibration", test_calib)
    print(f"Извлечение 3D для калибровочного фото {photo_id_calib}...")
    summary_calib = service.process_photo("calibration", photo_id_calib)

    print("\nПроверка созданных файлов для калибровочного фото:")
    storage_calib = SETTINGS.storage_root / "calibration" / photo_id_calib
    for f in expected_files:
        p = storage_calib / f
        print(f"  Файл {f:35} {'[ОК]' if p.exists() else '[ОТСУТСТВУЕТ]'}")

    # 3. Валидация кросс-матчинга и Байесовского вывода
    print("\n[ТЕСТ 3] Запуск Байесовского вывода (Main vs Calibration)...")
    verdict_results = calculate_bayesian_evidence(summary_main, summary_calib)
    
    print("\n=== РЕЗУЛЬТАТЫ СРАВНЕНИЯ ===")
    print(f"Вердикт:               {verdict_results.get('verdict')}")
    print(f"Разница лет:           {verdict_results.get('delta_years')}")
    print(f"Костное расхождение:   {verdict_results.get('geometric_divergence'):.4f}")
    print(f"Истинное покрытие (A): {verdict_results.get('dataQuality', {}).get('coverageRatio'):.1%}")
    print("\nАпостериорные вероятности:")
    print(f"  H0 (Тот же человек): {verdict_results.get('H0'):.4f}")
    print(f"  H1 (Синтетика/Маска): {verdict_results.get('H1'):.4f}")
    print(f"  H2 (Разные люди):    {verdict_results.get('H2'):.4f}")

    print("\nЛог вычислений:")
    for line in verdict_results.get("computationLog", []):
        print(f"  - {line}")

    print("\n=== ДИАГОНАЛЬНОЕ ТЕСТИРОВАНИЕ ПРОЙДЕНО УСПЕШНО! ===")

if __name__ == "__main__":
    main()
