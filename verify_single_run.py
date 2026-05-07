import sys
import json
from pathlib import Path

# Добавляем пути проекта
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.core.config import SETTINGS
from backend.core.service import ForensicWorkbenchService

def check_json_for_nans(data) -> bool:
    """Проверяет рекурсивно наличие NaN в структуре данных (будет True, если NaN найден)"""
    if isinstance(data, dict):
        return any(check_json_for_nans(v) for v in data.values())
    elif isinstance(data, list):
        return any(check_json_for_nans(v) for v in data)
    elif isinstance(data, float):
        import math
        return math.isnan(data)
    return False

def main():
    print("=== ЗАПУСК ВЕРИФИКАЦИИ ОДНОЙ ПАРЫ (ИСПРАВЛЕНИЕ NaN, ПОР И СИЛИКОНА) ===")
    
    # 1. Сканируем фото
    main_photos = sorted([p for p in SETTINGS.main_photos_dir.glob("*.jpg") if not p.name.startswith(".")])
    calib_photos = sorted([p for p in SETTINGS.calibration_dir.glob("*.jpg") if not p.name.startswith(".")])
    
    if not main_photos or not calib_photos:
        print("[ERR] Недостаточно фотографий для верификации.")
        return

    m_photo = main_photos[0]
    c_photo = calib_photos[0]
    
    print(f"Выбранное основное фото:   {m_photo.name}")
    print(f"Выбранное калибровочное:   {c_photo.name}")

    service = ForensicWorkbenchService(dataset_path=SETTINGS.main_photos_dir, case_name="verification_run")

    # 2. Обрабатываем основное фото
    print("\n[1/2] Обработка основного фото...")
    id_main = service._photo_id("main", m_photo)
    sum_main = service.process_photo("main", id_main)

    # 3. Обрабатываем калибровочное фото
    print("\n[2/2] Обработка калибровочного фото...")
    id_calib = service._photo_id("calibration", c_photo)
    sum_calib = service.process_photo("calibration", id_calib)

    # 4. Считываем сохраненные JSON-файлы с диска
    path_main = service._summary_path("main", id_main)
    path_calib = service._summary_path("calibration", id_calib)

    print("\n=== РЕЗУЛЬТАТЫ СИСТЕМНОГО ОПРОСА ВЫВОДА ===")
    for name, path in [("Основное фото", path_main), ("Калибровочное фото", path_calib)]:
        print(f"\nАнализ файла {name} ({path.name}):")
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            
            # Проверяем отсутствие NaN на уровне сырого текста JSON (стандарт RFC 4627)
            raw_text = path.read_text(encoding="utf-8")
            contains_raw_nan = "NaN" in raw_text
            contains_python_nan = check_json_for_nans(data)
            
            metrics = data.get("metrics", {})
            status_detail = data.get("status_detail", {})
            tf = data.get("texture_forensics", {})
            
            print(f"  - Валидность JSON (нет сырых NaN):   {'[ОК]' if not contains_raw_nan else '[КРИТИЧЕСКИЙ СБОЙ - НАЙДЕНЫ NaN!]'}")
            print(f"  - Пригодность (usable_for_comparison): {status_detail.get('usable_for_comparison')} (Тип: {type(status_detail.get('usable_for_comparison'))})")
            print(f"  - Текстурные поры (pore_density):     {metrics.get('texture_pore_density')} (Ожидается: >0.0)")
            print(f"  - Плотность пятен (spot_density):     {metrics.get('texture_spot_density')} (Ожидается: >0.0)")
            print(f"  - Вероятность маски (silicone_prob):  {metrics.get('texture_silicone_prob')} (Ожидается: >=0.0)")
            print(f"  - GLCM контраст (glcm_contrast):      {metrics.get('glcm_contrast')} (Ожидается: число, не null)")
            print(f"  - GLCM однородность (homogeneity):    {metrics.get('glcm_homogeneity')} (Ожидается: число, не null)")
            print(f"  - GLCM корреляция (correlation):      {metrics.get('glcm_correlation')} (Ожидается: число, не null)")
            print(f"  - Гладкое покрытие (global_smooth):   {metrics.get('texture_global_smoothness')} (Ожидается: число)")
            print(f"  - Наличие uv_wrinkle_energy:          {'{[ОБНАРУЖЕНА ОШИБКА]}' if 'uv_wrinkle_energy' in tf else '[УСПЕШНО УДАЛЕНА]'}")

    print("\n=== ВЕРИФИКАЦИОННЫЙ ЗАПУСК ЗАВЕРШЕН ===")

if __name__ == "__main__":
    main()
