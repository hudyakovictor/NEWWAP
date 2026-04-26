from core.chronology import build_timeline


def test_chronology_stays_inside_bucket():
    calibration_summary = {"buckets": {"frontal": {"metrics": {"jaw_width_ratio": {"mad": 0.01, "status": "stable"}}}}}
    records = [
        {
            "photo_id": "a",
            "filename": "1999_01_01.jpg",
            "date_str": "1999-01-01",
            "parsed_year": 1999,
            "bucket": "frontal",
            "metrics": {"jaw_width_ratio": 1.0},
        },
        {
            "photo_id": "b",
            "filename": "1999_06_01.jpg",
            "date_str": "1999-06-01",
            "parsed_year": 1999,
            "bucket": "right_profile",
            "metrics": {"jaw_width_ratio": 1.0},
        },
        {
            "photo_id": "c",
            "filename": "1999_01_20.jpg",
            "date_str": "1999-01-20",
            "parsed_year": 1999,
            "bucket": "frontal",
            "metrics": {"jaw_width_ratio": 1.0},
        },
    ]
    timeline = build_timeline(records, calibration_summary)
    profile = next(item for item in timeline if item["photo_id"] == "b")
    assert profile["comparison_with_previous"] is None

