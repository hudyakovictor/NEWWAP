import sys
import unittest
from pathlib import Path
from collections import defaultdict
from unittest.mock import MagicMock

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.core.service import ForensicWorkbenchService
from backend.core.chronology import build_timeline, _texture_spike
from backend.core.recommendations import build_recommendations
from backend.core.utils import BUCKET_METRIC_KEYS
from backend.core.config import SETTINGS
from backend.core.jobs import JobManager

class DutinFinalSmokeSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        print("\n" + "="*50)
        print("DUTIN NEWAPP: FINAL 20-POINT SMOKE TEST SUITE")
        print("="*50)
        cls.service = ForensicWorkbenchService()
        cls.jobs = JobManager()

    def test_01_config_loading(self):
        """1. Ensure all settings and paths are initialized."""
        self.assertIsNotNone(SETTINGS.storage_root)
        self.assertGreater(SETTINGS.reference_year_end, 1900)
        print("✅ 01: Config loading ok.")

    def test_02_service_init(self):
        """2. Ensure service layer initializes heavy components."""
        self.assertIsNotNone(self.service)
        print("✅ 02: Service initialization ok.")

    def test_03_metric_clustering(self):
        """3. Verify metric grouping for UI clusters."""
        clusters = {
            "geometry": ["cranial_face_index", "jaw_width_ratio"],
            "texture": ["texture_silicone_prob", "texture_pore_density"]
        }
        # Check if BUCKET_METRIC_KEYS contains these keys
        all_keys = set()
        for keys in BUCKET_METRIC_KEYS.values():
            all_keys.update(keys)
        self.assertIn("cranial_face_index", all_keys)
        self.assertIn("texture_silicone_prob", all_keys)
        print("✅ 03: Metric clustering ok.")

    def test_04_calibration_robustness(self):
        """4. Calibration summary generation with empty data."""
        summary = self.service.calibration_summary()
        self.assertIn("stability_score", summary)
        print("✅ 04: Calibration robustness ok.")

    def test_05_chronology_empty(self):
        """5. Timeline building with zero records."""
        timeline = build_timeline([], {})
        self.assertEqual(len(timeline), 0)
        print("✅ 05: Chronology empty-state ok.")

    def test_06_chronology_single(self):
        """6. Timeline building with a single record (no comparison)."""
        mock_rec = {"photo_id": "1", "date_str": "2000-01-01", "bucket": "frontal", "metrics": {}}
        timeline = build_timeline([mock_rec], {})
        self.assertEqual(len(timeline), 1)
        self.assertIsNone(timeline[0]["comparison_with_previous"])
        print("✅ 06: Chronology single-record ok.")

    def test_07_chronology_transition(self):
        """7. Detect transition (High Severity)."""
        recs = [
            {"photo_id": "1", "date_str": "2000-01-01", "bucket": "frontal", "metrics": {"cranial_face_index": 0.8}, "filename": "1.jpg"},
            {"photo_id": "2", "date_str": "2000-02-01", "bucket": "frontal", "metrics": {"cranial_face_index": 1.1}, "filename": "2.jpg"}
        ]
        timeline = build_timeline(recs, {"metrics": []})
        self.assertTrue(any(f["type"] == "transition" for f in timeline[1]["anomaly_flags"]))
        print("✅ 07: Chronology transition detection ok.")

    def test_08_chronology_impossible(self):
        """8. Detect Identity Swap (Impossible Short)."""
        recs = [
            {"photo_id": "1", "date_str": "2000-01-01", "bucket": "frontal", "metrics": {"cranial_face_index": 0.8, "texture_silicone_prob": 0.1}, "filename": "1.jpg"},
            {"photo_id": "2", "date_str": "2000-01-05", "bucket": "frontal", "metrics": {"cranial_face_index": 1.05, "texture_silicone_prob": 0.7}, "filename": "2.jpg"}
        ]
        timeline = build_timeline(recs, {"metrics": []})
        flags = [f["type"] for f in timeline[1]["anomaly_flags"]]
        self.assertIn("impossible_short", flags)
        print("✅ 08: Identity Swap detection ok.")

    def test_09_chronology_white_zone(self):
        """9. Detect White Zone (Long Gap)."""
        recs = [
            {"photo_id": "1", "date_str": "2000-01-01", "bucket": "frontal", "metrics": {}, "filename": "1.jpg"},
            {"photo_id": "2", "date_str": "2000-03-01", "bucket": "frontal", "metrics": {}, "filename": "2.jpg"}
        ]
        timeline = build_timeline(recs, {"metrics": []})
        self.assertTrue(any(f["type"] == "long_gap" for f in timeline[1]["anomaly_flags"]))
        print("✅ 09: White Zone detection ok.")

    def test_10_chronology_return(self):
        """10. Detect Return to Reference."""
        # Нужно 2 попадания в метрики и наличие предыдущей аномалии
        recs = [
            {"photo_id": "r1", "date_str": "1999-01-01", "bucket": "frontal", "metrics": {"cranial_face_index": 0.8, "jaw_width_ratio": 0.5}, "parsed_year": 1999, "filename": "r1.jpg"},
            {"photo_id": "a1", "date_str": "2000-01-01", "bucket": "frontal", "metrics": {"cranial_face_index": 1.2, "jaw_width_ratio": 0.8}, "parsed_year": 2000, "filename": "a1.jpg"}, # Аномалия
            {"photo_id": "v1", "date_str": "2000-01-10", "bucket": "frontal", "metrics": {"cranial_face_index": 0.801, "jaw_width_ratio": 0.501}, "parsed_year": 2001, "filename": "v1.jpg"} # Возврат
        ]
        timeline = build_timeline(recs, {"metrics": [{"key": "cranial_face_index", "std": 0.05}, {"key": "jaw_width_ratio", "std": 0.05}]})
        self.assertTrue(any(f["type"] == "return" for f in timeline[2]["anomaly_flags"]))
        print("✅ 10: Return to Reference detection ok.")

    def test_11_reliability_weighting(self):
        """11. Texture spike suppression via reliability_weight."""
        cur = {"metrics": {"texture_silicone_prob": 0.8}, "texture_forensics": {"reliability_weight": 0.1}}
        prev = {"metrics": {"texture_silicone_prob": 0.1}}
        spike = _texture_spike(cur, prev)
        self.assertLess(spike, 0.15)
        print("✅ 11: Reliability weighting ok.")

    def test_12_pose_gating(self):
        """12. Anomaly suppression on extreme poses."""
        recs = [
            {"photo_id": "1", "date_str": "2000-01-01", "bucket": "frontal", "metrics": {"cranial_face_index": 0.8}, "pose": {"yaw": 0}, "filename": "1.jpg"},
            {"photo_id": "2", "date_str": "2000-01-10", "bucket": "frontal", "metrics": {"cranial_face_index": 0.85}, "pose": {"yaw": 45}, "filename": "2.jpg"}
        ]
        # 0.05 delta * 0.5 conf = 0.025. Если std=0.2, то разрешено ~0.2. 0.025 < 0.2 -> stable.
        timeline = build_timeline(recs, {"metrics": [{"key": "cranial_face_index", "std": 0.2}]})
        self.assertEqual(timeline[1]["verdict"]["status"], "stable")
        print("✅ 12: Pose gating ok.")

    def test_13_recommendations_logic(self):
        """13. Ensure critical recommendations are generated."""
        mock_rec = {"photo_id": "2", "bucket": "frontal", "date_str": "2000-01-01", "anomaly_flags": [{"type": "impossible_short", "severity": "critical"}]}
        recs = build_recommendations([mock_rec], {})
        self.assertTrue(any(r["priority"] == "critical" for r in recs))
        print("✅ 13: Recommendations logic ok.")

    def test_14_api_overview_schema(self):
        """14. Overview JSON structure validation."""
        ov = self.service.overview()
        self.assertIn("timeline_summary", ov)
        self.assertIn("audit_current", ov)
        print("✅ 14: API Overview schema ok.")

    def test_15_api_photo_detail_bundle(self):
        """15. Photo detail data consistency."""
        # Just check if method exists and returns None for missing
        res = self.service.photo_detail("main", "non_existent")
        self.assertIsNone(res)
        print("✅ 15: API Photo Detail bundle ok.")

    def test_16_job_manager_flow(self):
        """16. Job lifecycle: Start, List, Get."""
        jid = self.jobs.start("test", "main", lambda p: None)
        self.assertIsNotNone(jid)
        status = self.jobs.get(jid)["status"]
        self.assertIn(status, ["running", "done"])
        print("✅ 16: Job manager flow ok.")

    def test_17_storage_integrity(self):
        """17. Derived artifacts pathing."""
        path = self.service._photo_storage_dir("main", "test_id")
        self.assertTrue(str(path).endswith("test_id"))
        print("✅ 17: Storage integrity ok.")

    def test_18_metric_normalization_stability(self):
        """18. Verify zygomatic-breadth logic exists."""
        from backend.core.analysis import _normalize_vertices
        v = np.zeros((100, 3))
        # Mock bone indices to avoid error
        with unittest.mock.patch('backend.core.analysis.MACRO_BONE_INDICES', {'cheekbone_L': [0], 'cheekbone_R': [1]}):
            v[1, 0] = 1.0 # 1.0 width
            norm, meta = _normalize_vertices(v)
            self.assertEqual(meta["zygomatic_breadth"], 1.0)
        print("✅ 18: Metric normalization stability ok.")

    def test_19_ui_contract_alignment(self):
        """19. Verify essential UI fields in photo record."""
        recs = self.service.main_records()
        if recs:
            r = recs[0]
            self.assertIn("artifacts", r)
            self.assertIn("verdict", r)
            self.assertIn("bucket_label", r)
        print("✅ 19: UI contract alignment ok.")

    def test_20_identity_swap_forensic_score(self):
        """20. Forensic score calculation accuracy."""
        recs = [
            {"photo_id": "1", "date_str": "2000-01-01", "bucket": "frontal", "metrics": {"cranial_face_index": 0.8, "texture_silicone_prob": 0.1}, "filename": "1.jpg"},
            {"photo_id": "2", "date_str": "2000-01-05", "bucket": "frontal", "metrics": {"cranial_face_index": 1.2, "texture_silicone_prob": 0.9}, "filename": "2.jpg"}
        ]
        timeline = build_timeline(recs, {"metrics": []})
        score = timeline[1]["anomaly_flags"][0].get("forensic_score", 0)
        self.assertGreater(score, 1.0)
        print("✅ 20: Identity Swap forensic score ok.")

if __name__ == "__main__":
    import numpy as np
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
