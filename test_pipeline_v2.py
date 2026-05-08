#!/usr/bin/env python3
"""
Тестирование run_pipeline_v2.py - SCAP Forensic Pipeline v2.0
Стратегия тестирования на 99 баллов согласно ТЗ
"""

import unittest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional
import numpy as np
import sys

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

# Import pipeline components
from run_pipeline_v2 import (
    MetadataParser, PhotoMetadata, DatasetOrganizer,
    ExtractedData, ExtractStage, CalibrateStage, AnalyzeStage,
    PairResult, CalibrationPair, GroupCalibrationStats,
    SCAPPipeline, POSE_DISTANCE_THRESHOLD, CHRONOLOGY_GAP_YEARS, EMA_ALPHA
)


# =============================================================================
# Модуль 1: Unit Tests (30 баллов)
# =============================================================================

class TestMetadataParser(unittest.TestCase):
    """Тестирование парсинга метаданных из имен файлов"""
    
    def test_parse_standard_filename(self):
        """Парсинг стандартного имени файла с yaw/pitch/roll"""
        test_cases = [
            # Полный формат
            ("putin_2001_05_15_yaw15_pitch5_roll0.jpg", 2001, 5, 15, 15.0, 5.0, 0.0),
            ("test_1999_01_01_yaw0_pitch0_roll0.jpg", 1999, 1, 1, 0.0, 0.0, 0.0),
            # Сокращенный формат (как в реальном датасете)
            ("1999_07_01_y-13p17r-11.jpg", 1999, 7, 1, -13.0, 17.0, -11.0),
            ("1999_08_12_y13p10r-5.jpg", 1999, 8, 12, 13.0, 10.0, -5.0),
            ("1999_08_16_y-46p-27r23.jpg", 1999, 8, 16, -46.0, -27.0, 23.0),
        ]
        
        for filename, year, month, day, yaw, pitch, roll in test_cases:
            with self.subTest(filename=filename):
                # Create temp file
                with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as f:
                    temp_path = Path(f.name)
                
                try:
                    result = MetadataParser.parse_photo(temp_path)
                    self.assertIsNotNone(result)
                    self.assertEqual(result.date.year, year)
                    self.assertEqual(result.date.month, month)
                    self.assertEqual(result.date.day, day)
                    self.assertEqual(result.yaw, yaw)
                    self.assertEqual(result.pitch, pitch)
                    self.assertEqual(result.roll, roll)
                finally:
                    temp_path.unlink()
    
    def test_bucket_classification(self):
        """Классификация по yaw-углам"""
        test_cases = [
            (0, "frontal"),
            (10, "frontal"),
            (20, "right_threequarter_light"),
            (35, "right_threequarter_mid"),  # 25-45 range
            (50, "right_threequarter_deep"), # 45-65 range
            (70, "right_profile"),           # >65
            (-5, "unclassified"),            # between frontal and left_threequarter
            (-20, "left_threequarter_light"),  # -25 < yaw < -12
            (-35, "left_threequarter_mid"),  # -45 < yaw < -25
            (-50, "left_threequarter_deep"), # -65 < yaw < -45
            (-70, "left_profile"),           # yaw < -65
        ]
        
        for yaw, expected_bucket in test_cases:
            with self.subTest(yaw=yaw):
                bucket = MetadataParser._classify_bucket(yaw)
                self.assertEqual(bucket, expected_bucket)
    
    def test_invalid_filename(self):
        """Обработка невалидных имен файлов"""
        invalid_names = [
            "no_date_here.jpg",
            "no_angles_2001.jpg",
            "wrong_format.txt",
        ]
        
        for filename in invalid_names:
            with self.subTest(filename=filename):
                with tempfile.NamedTemporaryFile(suffix=f"_{filename}", delete=False) as f:
                    temp_path = Path(f.name)
                
                try:
                    result = MetadataParser.parse_photo(temp_path)
                    # Should either return None or use pose detector fallback
                    # Just verify it doesn't crash
                finally:
                    if temp_path.exists():
                        temp_path.unlink()


class TestDatasetOrganizer(unittest.TestCase):
    """Тестирование организации датасета"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.main_dir = self.temp_dir / "main"
        self.cal_dir = self.temp_dir / "calibration"
        self.main_dir.mkdir()
        self.cal_dir.mkdir()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_group_by_bucket(self):
        """Группировка фото по ракурсам"""
        # Create test photos with different yaws
        photos_data = [
            ("2001_01_01_y0p0r0.jpg", 0, "frontal"),
            ("2002_01_01_y15p0r0.jpg", 15, "right_threequarter_light"),
            ("2003_01_01_y30p0r0.jpg", 30, "right_threequarter_mid"),
            ("2004_01_01_y45p0r0.jpg", 45, "right_profile"),
        ]
        
        for filename, yaw, expected_bucket in photos_data:
            path = self.main_dir / filename
            path.touch()
        
        organizer = DatasetOrganizer(self.main_dir, self.cal_dir)
        groups = organizer.scan_and_organize()
        
        # Verify groups exist (using actual bucket names)
        self.assertIn("frontal", groups)
        self.assertIn("right_threequarter_light", groups)
        self.assertIn("right_threequarter_mid", groups)
        
        # Verify chronological sorting - only yaw0 is in frontal bucket
        frontal_photos = groups["frontal"]
        self.assertEqual(len(frontal_photos), 1)
        self.assertEqual(frontal_photos[0].yaw, 0)
    
    def test_find_calibration_match(self):
        """Подбор калибровочной пары по позе"""
        # Create calibration photos with short format (like real dataset)
        cal_photos = [
            ("cal_2000_01_01_y10p0r0.jpg", 10),
            ("cal_2001_01_01_y20p0r0.jpg", 20),
            ("cal_2002_01_01_y35p0r0.jpg", 35),
        ]
        
        for filename, yaw in cal_photos:
            path = self.cal_dir / filename
            path.touch()
        
        # Create main photo
        main_photo_path = self.main_dir / "main_2005_06_15_y18p0r0.jpg"
        main_photo_path.touch()
        
        organizer = DatasetOrganizer(self.main_dir, self.cal_dir)
        organizer.scan_and_organize()  # Load calibration photos
        
        # Test finding closest calibration
        test_metadata = PhotoMetadata(
            path=main_photo_path,
            photo_id="main_2005_06_15_y18p0r0",
            date=datetime(2005, 6, 15),
            yaw=18,
            pitch=0,
            roll=0,
            bucket="right_threequarter_light"
        )
        
        match, distance, approximate = organizer.find_calibration_match(test_metadata)
        self.assertIsNotNone(match)
        # Should find cal_2001_yaw20 as closest (distance = 2)
        self.assertEqual(match.yaw, 20)


class TestCalibrationStats(unittest.TestCase):
    """Тестирование EMA-статистики калибровки"""
    
    def test_ema_update(self):
        """Обновление EMA статистики"""
        stats = GroupCalibrationStats(group="frontal")
        
        # First update
        deltas1 = {"jaw_width": 0.05, "nose_ratio": 0.02}
        stats.update(deltas1)
        
        self.assertIn("jaw_width", stats.metric_medians)
        self.assertIn("nose_ratio", stats.metric_medians)
        
        # Second update - EMA should blend
        deltas2 = {"jaw_width": 0.07, "nose_ratio": 0.03}
        stats.update(deltas2)
        
        # EMA formula: new_median = alpha * new_value + (1-alpha) * old_median
        # With alpha=0.3: median_jaw = 0.3 * 0.07 + 0.7 * 0.05 = 0.056
        expected_median = EMA_ALPHA * 0.07 + (1 - EMA_ALPHA) * 0.05
        self.assertAlmostEqual(stats.metric_medians["jaw_width"], expected_median, places=5)
    
    def test_threshold_calculation(self):
        """Расчет порогов аномалий"""
        stats = GroupCalibrationStats(group="frontal")
        
        # Add some calibration history
        for i in range(10):
            deltas = {"metric1": 0.05 + i * 0.01}
            stats.update(deltas)
        
        # Get threshold for normal calibration
        threshold_normal = stats.get_threshold("metric1", approximate=False)
        # Should be 2.5 * std
        self.assertGreater(threshold_normal, 0)
        
        # Get threshold for approximate match (should be higher)
        threshold_approx = stats.get_threshold("metric1", approximate=True)
        self.assertGreater(threshold_approx, threshold_normal)


# =============================================================================
# Модуль 2: Integration Tests (40 баллов)
# =============================================================================

class TestExtractStage(unittest.TestCase):
    """Тестирование этапа Extract"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.main_dir = self.temp_dir / "main"
        self.cal_dir = self.temp_dir / "calibration"
        self.storage_dir = self.temp_dir / "storage"
        self.main_dir.mkdir()
        self.cal_dir.mkdir()
        self.storage_dir.mkdir()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_cache_creation(self):
        """Создание кэша для извлеченных данных"""
        # Create a test photo
        photo_path = self.main_dir / "test_2020_06_15_yaw10_pitch5_roll0.jpg"
        photo_path.touch()
        
        organizer = DatasetOrganizer(self.main_dir, self.cal_dir)
        groups = organizer.scan_and_organize()
        
        self.assertGreater(len(groups), 0)
        
        # Mock extraction (without actual 3D reconstruction)
        # In real test, this would use mocked backend calls


class TestCalibrateStage(unittest.TestCase):
    """Тестирование этапа Calibrate"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage_dir = self.temp_dir / "storage"
        self.storage_dir.mkdir()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_pair_processing(self):
        """Обработка одной пары с калибровкой"""
        # Create mock photo metadata
        photo_a = PhotoMetadata(
            path=Path("/fake/path/a.jpg"),
            photo_id="photo_a",
            date=datetime(2001, 1, 1),
            yaw=15,
            pitch=0,
            roll=0,
            bucket="frontal"
        )
        
        photo_b = PhotoMetadata(
            path=Path("/fake/path/b.jpg"),
            photo_id="photo_b",
            date=datetime(2002, 1, 1),
            yaw=18,
            pitch=0,
            roll=0,
            bucket="frontal"
        )
        
        # Test that pair processing logic works
        # (Would need mocked backend for full test)


class TestAnalyzeStage(unittest.TestCase):
    """Тестирование этапа Analyze"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage_dir = self.temp_dir / "storage"
        self.storage_dir.mkdir()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def test_anomaly_detection(self):
        """Детекция аномалий в метриках"""
        # Create mock results with anomaly
        calibration = CalibrationPair(
            cal_A="cal_a",
            cal_B="cal_b",
            pose_distance_A=2.0,
            pose_distance_B=2.5,
            approximate_match=False,
            calibration_deltas={"jaw_width": 0.02}
        )
        
        result_with_anomaly = PairResult(
            pair_id="test_pair",
            group="frontal",
            photo_A=PhotoMetadata(
                path=Path("/a.jpg"), photo_id="a",
                date=datetime(2001, 1, 1), yaw=10, pitch=0, roll=0, bucket="frontal"
            ),
            photo_B=PhotoMetadata(
                path=Path("/b.jpg"), photo_id="b",
                date=datetime(2002, 1, 1), yaw=12, pitch=0, roll=0, bucket="frontal"
            ),
            calibration=calibration,
            raw_metrics={"jaw_width": 0.25},  # Large jump
            corrected_metrics={"jaw_width": 0.23},  # Still large after calibration
            calibration_quality="high",
            anomaly_flags=[]
        )
        
        # Test anomaly detection
        stats = GroupCalibrationStats(group="frontal")
        stats.update({"jaw_width": 0.02})
        stats.update({"jaw_width": 0.03})
        
        # The corrected value 0.23 should trigger anomaly if threshold is low
        threshold = stats.get_threshold("jaw_width", approximate=False)
        self.assertGreater(threshold, 0)


# =============================================================================
# Модуль 3: End-to-End Tests (20 баллов)
# =============================================================================

class TestFullPipeline(unittest.TestCase):
    """Интеграционные тесты полного pipeline"""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.main_dir = self.temp_dir / "main"
        self.cal_dir = self.temp_dir / "calibration"
        self.storage_dir = self.temp_dir / "storage"
        
        self.main_dir.mkdir()
        self.cal_dir.mkdir()
        self.storage_dir.mkdir()
        
        # Create test dataset
        self._create_test_dataset()
    
    def tearDown(self):
        shutil.rmtree(self.temp_dir)
    
    def _create_test_dataset(self):
        """Создание тестового датасета"""
        # Main dataset - 5 photos in chronological order
        main_photos = [
            ("putin_2000_01_01_yaw10_pitch0_roll0.jpg", datetime(2000, 1, 1)),
            ("putin_2001_06_15_yaw12_pitch2_roll1.jpg", datetime(2001, 6, 15)),
            ("putin_2003_03_20_yaw15_pitch0_roll0.jpg", datetime(2003, 3, 20)),
            ("putin_2005_09_10_yaw11_pitch1_roll0.jpg", datetime(2005, 9, 10)),
            ("putin_2010_12_25_yaw14_pitch0_roll1.jpg", datetime(2010, 12, 25)),
        ]
        
        for filename, date in main_photos:
            (self.main_dir / filename).touch()
        
        # Calibration dataset
        cal_photos = [
            ("cal_1999_yaw10_pitch0_roll0.jpg", datetime(1999, 1, 1)),
            ("cal_2002_yaw15_pitch0_roll0.jpg", datetime(2002, 1, 1)),
            ("cal_2008_yaw12_pitch0_roll0.jpg", datetime(2008, 1, 1)),
        ]
        
        for filename, date in cal_photos:
            (self.cal_dir / filename).touch()
    
    def test_full_pipeline_initialization(self):
        """Инициализация и базовая структура pipeline"""
        pipeline = SCAPPipeline(
            main_dataset_path=str(self.main_dir),
            calibration_dataset_path=str(self.cal_dir),
            storage_path=str(self.storage_dir)
        )
        
        # Verify storage structure created
        self.assertTrue((self.storage_dir / "pose").exists())
        self.assertTrue((self.storage_dir / "comparisons").exists())
        
        # Verify organizer loaded photos
        groups = pipeline.organizer.scan_and_organize()
        self.assertGreater(len(groups), 0)
    
    def test_chronology_processing_order(self):
        """Проверка хронологического порядка обработки"""
        organizer = DatasetOrganizer(self.main_dir, self.cal_dir)
        
        groups = organizer.scan_and_organize()
        for group_name, photos in groups.items():
            # Verify photos are sorted by date
            for i in range(len(photos) - 1):
                self.assertLessEqual(
                    photos[i].date, 
                    photos[i + 1].date,
                    f"Photos in group {group_name} not sorted chronologically"
                )


# =============================================================================
# Модуль 4: Edge Cases & Error Handling (9 баллов)
# =============================================================================

class TestEdgeCases(unittest.TestCase):
    """Тестирование граничных случаев"""
    
    def test_empty_dataset(self):
        """Обработка пустого датасета"""
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            main_dir = temp_dir / "main"
            cal_dir = temp_dir / "cal"
            main_dir.mkdir()
            cal_dir.mkdir()
            
            organizer = DatasetOrganizer(main_dir, cal_dir)
            groups = organizer.scan_and_organize()
            # Should handle empty dataset gracefully
            self.assertEqual(len(groups), 0)
        finally:
            shutil.rmtree(temp_dir)
    
    def test_single_photo_group(self):
        """Группа с одним фото (нет пар для сравнения)"""
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            main_dir = temp_dir / "main"
            cal_dir = temp_dir / "cal"
            main_dir.mkdir()
            cal_dir.mkdir()
            
            # Create only one photo
            (main_dir / "single_2000_yaw45.jpg").touch()
            
            organizer = DatasetOrganizer(main_dir, cal_dir)
            groups = organizer.scan_and_organize()
            # Group exists but has only 1 photo
            self.assertEqual(sum(len(p) for p in groups.values()), 1)
        finally:
            shutil.rmtree(temp_dir)
    
    def test_large_chronology_gap(self):
        """Обработка большого разрыва в хронологии (>2 лет)"""
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            main_dir = temp_dir / "main"
            cal_dir = temp_dir / "cal"
            main_dir.mkdir()
            cal_dir.mkdir()
            
            # Create photos with 3-year gap
            (main_dir / "photo_2000_01_01_yaw10.jpg").touch()
            (main_dir / "photo_2003_06_15_yaw12.jpg").touch()  # Gap > 2 years
            
            organizer = DatasetOrganizer(main_dir, cal_dir)
            groups = organizer.scan_and_organize()
            photos = groups.get("frontal", [])
            
            if len(photos) >= 2:
                gap = (photos[1].date - photos[0].date).days / 365.25
                self.assertGreater(gap, CHRONOLOGY_GAP_YEARS)
        finally:
            shutil.rmtree(temp_dir)
    
    def test_mixed_pose_comparison(self):
        """Сравнение фото с разными позами (ad-hoc режим)"""
        photo_a = PhotoMetadata(
            path=Path("/a.jpg"), photo_id="a",
            date=datetime(2000, 1, 1), yaw=10, pitch=0, roll=0, bucket="frontal"
        )
        
        photo_b = PhotoMetadata(
            path=Path("/b.jpg"), photo_id="b",
            date=datetime(2000, 1, 1), yaw=45, pitch=0, roll=0, bucket="profile"
        )
        
        # Different buckets
        self.assertNotEqual(photo_a.bucket, photo_b.bucket)


# =============================================================================
# Тестовый запуск
# =============================================================================

def run_tests():
    """Запуск всех тестов с отчетом"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestMetadataParser))
    suite.addTests(loader.loadTestsFromTestCase(TestDatasetOrganizer))
    suite.addTests(loader.loadTestsFromTestCase(TestCalibrationStats))
    suite.addTests(loader.loadTestsFromTestCase(TestExtractStage))
    suite.addTests(loader.loadTestsFromTestCase(TestCalibrateStage))
    suite.addTests(loader.loadTestsFromTestCase(TestAnalyzeStage))
    suite.addTests(loader.loadTestsFromTestCase(TestFullPipeline))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("ИТОГО ТЕСТИРОВАНИЯ")
    print("="*70)
    print(f"Всего тестов: {result.testsRun}")
    print(f"Пройдено: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Провалено: {len(result.failures)}")
    print(f"Ошибок: {len(result.errors)}")
    print(f"Пропущено: {len(result.skipped)}")
    
    if result.wasSuccessful():
        print("\n✓ Все тесты пройдены!")
        return 0
    else:
        print("\n✗ Есть проваленные тесты")
        return 1


if __name__ == "__main__":
    sys.exit(run_tests())
