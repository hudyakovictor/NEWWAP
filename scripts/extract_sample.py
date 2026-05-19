import logging
import random
from pathlib import Path
from backend.core.service import ForensicWorkbenchService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run():
    service = ForensicWorkbenchService()
    
    # 1. Сначала извлечем то самое проблемное фото, чтобы пользователь мог его проверить
    target_photo = "2000_05_07_y-34p0r0"
    try:
        logging.info(f"Extracting target photo: {target_photo}")
        service.process_photo("main", target_photo)
    except Exception as e:
        logging.error(f"Failed to extract target photo: {e}")

    # 2. Теперь извлечем 20 случайных фото из main
    all_records = service.list_dataset("main")
    
    # Фильтруем те, которые еще не извлечены
    unextracted = [r for r in all_records if r.get("status") == "not_extracted" and r.get("photo_id") != target_photo]
    
    # Выбираем 20 случайных
    sample = random.sample(unextracted, min(20, len(unextracted)))
    
    success = 0
    for idx, record in enumerate(sample):
        photo_id = record["photo_id"]
        logging.info(f"[{idx+1}/{len(sample)}] Extracting {photo_id}...")
        try:
            service.process_photo("main", photo_id)
            success += 1
        except Exception as e:
            logging.error(f"Error extracting {photo_id}: {e}")
            
    logging.info(f"Done! Successfully extracted {success + 1} photos.")

if __name__ == "__main__":
    run()
