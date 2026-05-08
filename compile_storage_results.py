#!/usr/bin/env python3
import os
import json
import csv
from pathlib import Path
from datetime import datetime

def compile_results(storage_path_str: str):
    storage_path = Path(storage_path_str)
    pose_path = storage_path / "pose"
    cal_path = storage_path / "calibration"
    
    print(f"Starting compilation of results from {storage_path}...")
    
    # 1. Сбор информации по всем фотографиям
    photos_data = []
    
    # Сбор основных фото (из папки pose)
    if pose_path.exists():
        for p_dir in pose_path.iterdir():
            if not p_dir.is_dir():
                continue
            photo_data_file = p_dir / "photo_data.json"
            if photo_data_file.exists():
                try:
                    with open(photo_data_file, 'r') as f:
                        meta = json.load(f)
                    photos_data.append({
                        "photo_id": meta["photo_id"],
                        "dataset_type": "main",
                        "date": meta["date"],
                        "yaw": meta["pose"]["yaw"],
                        "pitch": meta["pose"]["pitch"],
                        "roll": meta["pose"]["roll"],
                        "bucket": meta["pose"].get("bucket", "unclassified"),
                        "expression_jaw_open": meta.get("expression_flags", {}).get("jaw_open", False),
                        "expression_smile": meta.get("expression_flags", {}).get("smile", False),
                        "path": meta.get("path", "")
                    })
                except Exception as e:
                    print(f"Error reading {photo_data_file}: {e}")
                    
    # Сбор калибровочных фото
    if cal_path.exists():
        for p_dir in cal_path.iterdir():
            if not p_dir.is_dir():
                continue
            photo_data_file = p_dir / "photo_data.json"
            if photo_data_file.exists():
                try:
                    with open(photo_data_file, 'r') as f:
                        meta = json.load(f)
                    photos_data.append({
                        "photo_id": meta["photo_id"],
                        "dataset_type": "calibration",
                        "date": meta["date"],
                        "yaw": meta["pose"]["yaw"],
                        "pitch": meta["pose"]["pitch"],
                        "roll": meta["pose"]["roll"],
                        "bucket": meta["pose"].get("bucket", "unclassified"),
                        "expression_jaw_open": meta.get("expression_flags", {}).get("jaw_open", False),
                        "expression_smile": meta.get("expression_flags", {}).get("smile", False),
                        "path": meta.get("path", "")
                    })
                except Exception as e:
                    print(f"Error reading calibration {photo_data_file}: {e}")

    # Запись master_photos.csv
    photos_csv_path = storage_path / "master_photos.csv"
    with open(photos_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "photo_id", "dataset_type", "date", "yaw", "pitch", "roll", 
            "bucket", "expression_jaw_open", "expression_smile", "path"
        ])
        writer.writeheader()
        writer.writerows(photos_data)
    print(f"Saved {len(photos_data)} photos to {photos_csv_path}")

    # 2. Сбор информации по парам, метрикам и аномалиям
    pairs_data = []
    metrics_data = []
    anomalies_data = []
    
    if pose_path.exists():
        for p_dir in pose_path.iterdir():
            if not p_dir.is_dir():
                continue
            next_file = p_dir / "pair_with_next.json"
            if next_file.exists():
                try:
                    with open(next_file, 'r') as f:
                        data = json.load(f)
                    
                    pair_id = data["pair_id"]
                    group = data["group"]
                    photo_A = p_dir.name
                    photo_B = data["other_photo"]["id"]
                    photo_B_date = data["other_photo"]["date"]
                    
                    cal_quality = data["calibration"]["quality"]
                    cal_A = data["calibration"]["cal_A"]
                    cal_B = data["calibration"]["cal_B"]
                    dist_A = data["calibration"]["pose_distance_A"]
                    dist_B = data["calibration"]["pose_distance_B"]
                    approx_match = data["calibration"]["approximate_match"]
                    
                    anomalies = data.get("anomalies", [])
                    anomalies_count = len(anomalies)
                    
                    # Сохраняем сводку по паре
                    pairs_data.append({
                        "pair_id": pair_id,
                        "group": group,
                        "photo_A": photo_A,
                        "photo_B": photo_B,
                        "photo_B_date": photo_B_date,
                        "calibration_quality": cal_quality,
                        "calibration_A": cal_A,
                        "calibration_B": cal_B,
                        "pose_distance_A": dist_A,
                        "pose_distance_B": dist_B,
                        "approximate_match": approx_match,
                        "anomalies_count": anomalies_count
                    })
                    
                    # Сохраняем детальные метрики (длинный формат)
                    raw_metrics = data.get("metrics", {}).get("raw", {})
                    corrected_metrics = data.get("metrics", {}).get("corrected", {})
                    
                    all_metric_names = set(raw_metrics.keys()).union(corrected_metrics.keys())
                    for metric_name in all_metric_names:
                        metrics_data.append({
                            "pair_id": pair_id,
                            "group": group,
                            "photo_A": photo_A,
                            "photo_B": photo_B,
                            "metric_name": metric_name,
                            "raw_value": raw_metrics.get(metric_name, ""),
                            "corrected_value": corrected_metrics.get(metric_name, "")
                        })
                        
                    # Сохраняем аномалии
                    for anomaly in anomalies:
                        anomalies_data.append({
                            "pair_id": pair_id,
                            "group": group,
                            "photo_A": photo_A,
                            "photo_B": photo_B,
                            "metric_name": anomaly["metric"],
                            "value": anomaly["value"],
                            "threshold": anomaly["threshold"],
                            "severity": anomaly["severity"]
                        })
                        
                except Exception as e:
                    print(f"Error reading pair result {next_file}: {e}")

    # Запись master_pairs.csv
    pairs_csv_path = storage_path / "master_pairs.csv"
    with open(pairs_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "pair_id", "group", "photo_A", "photo_B", "photo_B_date",
            "calibration_quality", "calibration_A", "calibration_B",
            "pose_distance_A", "pose_distance_B", "approximate_match", "anomalies_count"
        ])
        writer.writeheader()
        writer.writerows(pairs_data)
    print(f"Saved {len(pairs_data)} pairs to {pairs_csv_path}")

    # Запись master_metrics.csv
    metrics_csv_path = storage_path / "master_metrics.csv"
    with open(metrics_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "pair_id", "group", "photo_A", "photo_B", "metric_name", "raw_value", "corrected_value"
        ])
        writer.writeheader()
        writer.writerows(metrics_data)
    print(f"Saved {len(metrics_data)} metrics to {metrics_csv_path}")

    # Запись master_anomalies.csv
    anomalies_csv_path = storage_path / "master_anomalies.csv"
    with open(anomalies_csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "pair_id", "group", "photo_A", "photo_B", "metric_name", "value", "threshold", "severity"
        ])
        writer.writeheader()
        writer.writerows(anomalies_data)
    print(f"Saved {len(anomalies_data)} anomalies to {anomalies_csv_path}")

    # 3. Сохранение единой JSON структуры для фронтенда (все в одном)
    master_json_path = storage_path / "master_ui_data.json"
    master_ui_payload = {
        "summary": {
            "total_photos": len(photos_data),
            "total_pairs": len(pairs_data),
            "total_anomalies": len(anomalies_data),
            "timestamp": datetime.now().isoformat()
        },
        "photos": photos_data,
        "pairs": pairs_data,
        "anomalies": anomalies_data
    }
    
    with open(master_json_path, 'w', encoding='utf-8') as f:
        json.dump(master_ui_payload, f, indent=2, ensure_ascii=False)
    print(f"Saved consolidated master UI JSON to {master_json_path}")
    
    print("Compilation completed successfully!")

if __name__ == "__main__":
    compile_results("/Volumes/SDCARD/storage")
