import sys
from pathlib import Path
import numpy as np

# Добавляем пути проекта
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.core.compare import InvestigationEngine

def main():
    print("==================================================")
    print("      DEEPUTIN FORENSIC PAIRWISE MATRIX (H0)")
    print("==================================================\n")
    
    summary_dir = Path("/Volumes/SDCARD/storage/main")
    engine = InvestigationEngine(summary_dir)
    
    keys = list(engine.vectors.keys())
    matrix = engine.compute_n_x_n_matrix()
    
    # Печатаем шапку таблицы
    header = f"{'Photo ID':<30}"
    for k in keys:
        header += f" | {k[:10]:<10}"
    print(header)
    print("-" * len(header))
    
    # Печатаем строки матрицы
    for i, row_key in enumerate(keys):
        row_str = f"{row_key:<30}"
        for j in range(len(keys)):
            val = matrix[i][j] if i != j else 1.0
            row_str += f" | {val:.4f}"
        print(row_str)
        
    print("\n==================================================")
    print(" Легенда: H0 >= 0.70 - Одно лицо (Высокая уверенность)")
    print("          H0 < 0.40  - Аномалия/Разные люди")
    print("==================================================")

if __name__ == "__main__":
    main()
