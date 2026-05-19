import logging
import random
from backend.core.service import ForensicWorkbenchService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def run():
    service = ForensicWorkbenchService()
    
    # Извлечем 20 случайных фото из calibration
    all_records = service.list_dataset("calibration")
    
    # Фильтруем те, которые еще не извлечены
    unextracted = [r for r in all_records if r.get("status") == "not_extracted"]
    
    # Выбираем 20 случайных
    sample = random.sample(unextracted, min(20, len(unextracted)))
    
    success = 0
    for idx, record in enumerate(sample):
        photo_id = record["photo_id"]
        logging.info(f"[{idx+1}/{len(sample)}] Extracting CALIBRATION {photo_id}...")
        try:
            service.process_photo("calibration", photo_id)
            success += 1
        except Exception as e:
            logging.error(f"Error extracting {photo_id}: {e}")
            
    logging.info(f"Done! Successfully extracted {success} calibration photos.")

if __name__ == "__main__":
    run()
