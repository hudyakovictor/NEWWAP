import json
from pathlib import Path

def aggregate_folder(storage_path: Path, output_file: Path):
    print(f"Scanning folder: {storage_path}")
    aggregated = {}
    
    # Рекурсивно ищем все summary.json (или *_summary.json), исключая скрытые файлы macOS
    json_files = [
        p for p in list(storage_path.glob("**/summary.json")) + list(storage_path.glob("**/*_summary.json"))
        if not p.name.startswith(".") and not p.parent.name.startswith(".")
    ]
    
    # Убираем дубликаты путей
    unique_files = sorted(list(set(json_files)))
    
    for idx, p in enumerate(unique_files):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = json.load(f)
                
            # Используем имя родительской папки (ID фото) в качестве ключа
            photo_id = p.parent.name
            aggregated[photo_id] = data
        except Exception as e:
            print(f"Error reading {p.name}: {e}")
            
    # Сохраняем агрегированную таблицу в корневую репозитория
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(aggregated, f, ensure_ascii=False, indent=2)
        
    print(f"Successfully aggregated {len(aggregated)} records to {output_file.name}")

def main():
    storage_root = Path("/Volumes/SDCARD/storage")
    repo_root = Path(__file__).resolve().parent
    
    main_output = repo_root / "main_aggregated.json"
    calib_output = repo_root / "calibration_aggregated.json"
    
    aggregate_folder(storage_root / "main", main_output)
    aggregate_folder(storage_root / "calibration", calib_output)

if __name__ == "__main__":
    main()
