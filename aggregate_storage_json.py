import os
import json
from pathlib import Path

def aggregate_dataset_json(dataset_name: str) -> list[dict]:
    storage_dir = Path(f"/Volumes/SDCARD/storage/{dataset_name}")
    aggregated_data = []
    
    if not storage_dir.exists():
        print(f"[PRED] Директория хранилища для '{dataset_name}' не найдена.")
        return aggregated_data

    # Сканируем все подпапки в поисках summary.json
    summary_files = list(storage_dir.glob("**/summary.json"))
    print(f"Найдено {len(summary_files)} файлов summary.json для '{dataset_name}'")
    
    for sf in sorted(summary_files):
        try:
            with sf.open("r", encoding="utf-8") as file:
                data = json.load(file)
                aggregated_data.append(data)
        except Exception as e:
            print(f"  [ERR] Ошибка чтения {sf}: {e}")
            
    return aggregated_data

def main():
    print("=== ЗАПУСК ПАКЕТНОЙ АГРЕГАЦИИ СУДЕБНО-МЕДИЦИНСКИХ JSON ===")
    
    # 1. Агрегируем main
    main_data = aggregate_dataset_json("main")
    main_output = Path("/Users/victorkhudyakov/dutin/newapp/main_aggregated.json")
    with main_output.open("w", encoding="utf-8") as f:
        json.dump(main_data, f, indent=4, ensure_ascii=False)
    print(f"[ОК] Агрегированные данные основного анализа сохранены в: {main_output} (Всего записей: {len(main_data)})")

    # 2. Агрегируем калибровку
    calib_data = aggregate_dataset_json("calibration")
    calib_output = Path("/Users/victorkhudyakov/dutin/newapp/calibration_aggregated.json")
    with calib_output.open("w", encoding="utf-8") as f:
        json.dump(calib_data, f, indent=4, ensure_ascii=False)
    print(f"[ОК] Агрегированные данные калибровки сохранены в: {calib_output} (Всего записей: {len(calib_data)})")

if __name__ == "__main__":
    main()
