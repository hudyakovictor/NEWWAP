#!/usr/bin/env python3
import argparse
import logging
import sys
from pathlib import Path

# Ensure backend and core are in python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.core.service import ForensicWorkbenchService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("forensic_pipeline")

def main():
    parser = argparse.ArgumentParser(description="DEEPUTIN Forensic Pipeline CLI (Strict Stage Separation)")
    parser.add_argument("--mode", required=True, choices=["extract", "matrix"], help="Pipeline execution mode")
    parser.add_argument("--dataset", required=True, help="Path to input photo dataset")
    parser.add_argument("--case_name", default="case_default", help="Unique identifier for the analysis session")
    args = parser.parse_args()

    # Инициализация сервиса (без UI, только бекенд)
    service = ForensicWorkbenchService(dataset_path=args.dataset, case_name=args.case_name)

    if args.mode == "extract":
        logger.info("Запуск Offline Extraction (Stage 1)...")
        # Извлекаем сырые данные строго 1 раз для каждого фото
        service.process_dataset(force_recompute=False)
        
    elif args.mode == "matrix":
        logger.info("Запуск Online Inference (Сравнение N x N)...")
        # Работаем только с готовыми JSON, не трогая GPU и 3DDFA
        service.compute_pairwise_matrix()

if __name__ == "__main__":
    main()
