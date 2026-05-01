#!/usr/bin/env python3
"""
Log rotation utility for DEEPUTIN project.

Manages log files in the project's logs/ directory:
- Backend API logs (requests, errors, pipeline events)
- Pipeline run logs (per-stage output)
- Audit logs (invariant results over time)

Usage:
  python scripts/log_rotate.py                    # Rotate all logs
  python scripts/log_rotate.py --max-size 10      # Max size in MB (default: 10)
  python scripts/log_rotate.py --keep 7           # Keep N rotated copies (default: 7)
"""

import os
import sys
import glob
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
MAX_SIZE_MB = 10
KEEP_COPIES = 7

def rotate_log(log_path: Path, max_mb: int = MAX_SIZE_MB, keep: int = KEEP_COPIES):
    """Rotate a single log file if it exceeds max_mb."""
    if not log_path.exists():
        return
    
    size_mb = log_path.stat().st_size / (1024 * 1024)
    if size_mb < max_mb:
        return
    
    # Rotate: .log → .log.1, .log.1 → .log.2, etc.
    for i in range(keep, 0, -1):
        src = log_path.parent / f"{log_path.name}.{i}"
        dst = log_path.parent / f"{log_path.name}.{i + 1}"
        if src.exists():
            if i >= keep:
                src.unlink()  # Delete oldest
            else:
                src.rename(dst)
    
    # Move current log to .1
    log_path.rename(log_path.parent / f"{log_path.name}.1")
    # Create fresh log file
    log_path.touch()

def main():
    max_mb = MAX_SIZE_MB
    keep = KEEP_COPIES
    
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--max-size" and i + 1 < len(args):
            max_mb = int(args[i + 1])
            i += 2
        elif args[i] == "--keep" and i + 1 < len(args):
            keep = int(args[i + 1])
            i += 2
        else:
            i += 1
    
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    
    log_files = list(LOG_DIR.glob("*.log"))
    if not log_files:
        print(f"[log_rotate] Нет файлов логов в {LOG_DIR}")
        return
    
    for lf in log_files:
        size_mb = lf.stat().st_size / (1024 * 1024)
        if size_mb >= max_mb:
            print(f"[rotate] {lf.name} ({size_mb:.1f} MB) → ротация")
            rotate_log(lf, max_mb, keep)
        else:
            print(f"[ok] {lf.name} ({size_mb:.1f} MB) — в пределах лимита")

if __name__ == "__main__":
    main()
