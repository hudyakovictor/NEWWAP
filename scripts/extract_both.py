import logging
import random
from backend.core.service import ForensicWorkbenchService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def extract_subset(service, dataset_name, count=10):
    all_records = service.list_dataset(dataset_name)
    unextracted = [r for r in all_records if r.get("status") == "not_extracted"]
    
    sample = random.sample(unextracted, min(count, len(unextracted)))
    
    success = 0
    for idx, record in enumerate(sample):
        photo_id = record["photo_id"]
        logging.info(f"[{dataset_name.upper()}] [{idx+1}/{len(sample)}] Extracting {photo_id}...")
        try:
            service.process_photo(dataset_name, photo_id)
            success += 1
        except Exception as e:
            logging.error(f"Error extracting {photo_id}: {e}")
            
    logging.info(f"Done! Extracted {success} photos for {dataset_name}.")

def run():
    service = ForensicWorkbenchService()
    extract_subset(service, "main", 10)
    extract_subset(service, "calibration", 10)

if __name__ == "__main__":
    run()
