from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from .config import SETTINGS
from .utils import ALL_BUCKETS, BUCKET_LABELS


def build_recommendations(
    main_records: list[dict[str, Any]],
    calibration_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    coverage = Counter(record.get("bucket") for record in main_records)
    calibration_coverage = calibration_summary.get("bucket_coverage", {})

    for bucket in ALL_BUCKETS:
        count = int(coverage.get(bucket, 0))
        cal_count = int(calibration_coverage.get(bucket, 0))
        if count == 0:
            recommendations.append(
                {
                    "type": "coverage_main",
                    "priority": "high",
                    "bucket": bucket,
                    "title": f"Нет основного покрытия по ракурсу «{BUCKET_LABELS[bucket]}»",
                    "description": "Без этого ракурса хронология внутри pose-bucket неполная.",
                    "benefit": "Появится непрерывная линия сравнения по соответствующему углу.",
                }
            )
        elif count < 3:
            recommendations.append(
                {
                    "type": "coverage_main",
                    "priority": "medium",
                    "bucket": bucket,
                    "title": f"Мало фото в ракурсе «{BUCKET_LABELS[bucket]}»",
                    "description": f"Сейчас только {count} кадра(ов), статистика слишком хрупкая.",
                    "benefit": "Меньше ложных переходов и лучше подтверждение возвратов.",
                }
            )
        if cal_count < 2:
            recommendations.append(
                {
                    "type": "coverage_calibration",
                    "priority": "medium",
                    "bucket": bucket,
                    "title": f"Слабая калибровка по «{BUCKET_LABELS[bucket]}»",
                    "description": f"Калибровочных кадров всего {cal_count}.",
                    "benefit": "Уже будут уже диапазоны шума и надёжнее допуски по метрикам.",
                }
            )

    for record in main_records:
        comparison = record.get("comparison_with_previous")
        if comparison and comparison.get("daysBetween", 0) > 30:
            prev_date = date.fromisoformat(comparison["previousDate"])
            next_date = date.fromisoformat(record["date_str"])
            midpoint = prev_date + timedelta(days=max(1, (next_date - prev_date).days // 2))
            recommendations.append(
                {
                    "type": "temporal_gap",
                    "priority": "high",
                    "bucket": record.get("bucket"),
                    "photo_id": record.get("photo_id"),
                    "title": f"Закрыть белую зону в «{BUCKET_LABELS.get(record.get('bucket'), record.get('bucket'))}»",
                    "description": f"Между {comparison['previousDate']} и {record['date_str']} разрыв {comparison['daysBetween']} дней.",
                    "benefit": f"Фото около {midpoint.isoformat()} сузит окно неопределённости по моменту перехода.",
                }
            )
        for flag in record.get("anomaly_flags", []):
            if flag.get("type") in {"transition", "impossible_short"}:
                f_score = flag.get("forensic_score", 0.0)
                is_swap = flag.get("type") == "impossible_short"
                
                title = f"Нужны соседние кадры вокруг {record.get('date_str')}"
                if is_swap:
                    title = f"Критическая аномалия (Identity Swap) в ракурсе {BUCKET_LABELS.get(record.get('bucket'), record.get('bucket'))}"
                
                desc = flag.get("description", "")
                if f_score >= 1.0:
                    desc += f" [Forensic Confidence: {f_score:.2f}]. Высокое сочетание геометрических и текстурных отклонений."

                recommendations.append(
                    {
                        "type": "anomaly_followup",
                        "priority": "critical" if is_swap else "high",
                        "bucket": record.get("bucket"),
                        "photo_id": record.get("photo_id"),
                        "title": title,
                        "description": desc,
                        "benefit": "Позволит подтвердить подмену личности или выявить ошибку экстракции.",
                    }
                )
                break

    for metric in calibration_summary.get("metrics", []):
        if metric.get("status") != "replace":
            continue
        recommendations.append(
            {
                "type": "metric_replace",
                "priority": "medium",
                "bucket": metric.get("bucket"),
                "title": f"Метрику {metric.get('key')} стоит заменить или понизить",
                "description": "На калибровке она ведёт себя слишком шумно.",
                "benefit": "Таймлайн станет чище, а ложные аномалии уйдут.",
            }
        )

    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    recommendations.sort(key=lambda item: (priority_order.get(item["priority"], 3), item["title"]))
    return recommendations[: SETTINGS.max_recommendations]

