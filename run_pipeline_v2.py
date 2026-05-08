#!/usr/bin/env python3
"""
DEEPUTIN Forensic Pipeline v2.0 - Sequential Calibration-Aware Pipeline (SCAP)

Трехэтапный pipeline: Extract → Calibrate → Analyze
Особенности:
- Линейная сложность (N-1 сравнений вместо N×N)
- Динамическая калибровка каждой хронологической пары
- EMA-обновление калибровочной статистики
- Предустановленные углы из имен файлов
- Последовательная обработка внутри групп ракурсов
"""

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
from tqdm import tqdm

# Ensure backend is in python path
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

from backend.core.service import ForensicWorkbenchService
from backend.pipeline.detect_pose import PoseDetector
from backend.pipeline.reconstruction import ReconstructionAdapter
from backend.pipeline.scoring import score_aligned_pair
from backend.pipeline.alignment import align_canonical_pair_for_view_group, canonicalize_vertices_for_bucket
from backend.pipeline.zones import compute_zone_metrics, apply_expression_exclusion_mask
from backend.pipeline.texture import SkinTextureAnalyzer
from backend.core.calibration import build_calibration_summary, pose_distance
from backend.core.chronology import build_timeline, build_timeline_summary
from backend.core.analysis import extract_photo_bundle, calculate_bayesian_evidence

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("pipeline2")


# =============================================================================
# Конфигурация и константы
# =============================================================================

BUCKET_THRESHOLDS = {
    "frontal": (0, 12),
    "left_threequarter_light": (-25, -12),
    "right_threequarter_light": (12, 25),
    "left_threequarter_mid": (-45, -25),
    "right_threequarter_mid": (25, 45),
    "left_threequarter_deep": (-65, -45),
    "right_threequarter_deep": (45, 65),
    "left_profile": (float('-inf'), -65),
    "right_profile": (65, float('inf')),
}

BUCKET_METRIC_KEYS = {
    "frontal": [
        "cranial_face_index", "jaw_width_ratio", "canthal_tilt_L", "canthal_tilt_R",
        "chin_offset_asymmetry", "nose_width_ratio", "nose_projection_ratio",
        "nasal_frontal_index", "nasofacial_angle_ratio", "chin_projection_ratio",
        "gonial_angle_L", "gonial_angle_R", "orbital_asymmetry_index",
        "interorbital_ratio", "forehead_slope_index", "orbit_depth_L_ratio",
        "orbit_depth_R_ratio", "texture_silicone_prob", "texture_pore_density",
        "texture_spot_density", "texture_wrinkle_forehead", "texture_wrinkle_nasolabial",
        "texture_global_smoothness", "texture_specular_gloss", "texture_lbp_complexity"
    ],
    "left_threequarter_light": [
        "cranial_face_index", "forehead_slope_index", "orbit_depth_L_ratio",
        "canthal_tilt_L", "canthal_tilt_R", "orbital_asymmetry_index", "interorbital_ratio",
        "nose_projection_ratio", "nasal_frontal_index", "nose_width_ratio",
        "jaw_width_ratio", "gonial_angle_L", "chin_projection_ratio",
        "nasofacial_angle_ratio", "chin_offset_asymmetry", "texture_silicone_prob",
        "texture_pore_density", "texture_spot_density", "texture_wrinkle_forehead",
        "texture_wrinkle_nasolabial", "texture_global_smoothness", "texture_specular_gloss",
        "texture_lbp_complexity"
    ],
    "right_threequarter_light": [
        "cranial_face_index", "forehead_slope_index", "orbit_depth_R_ratio",
        "canthal_tilt_R", "canthal_tilt_L", "orbital_asymmetry_index", "interorbital_ratio",
        "nose_projection_ratio", "nasal_frontal_index", "nose_width_ratio",
        "jaw_width_ratio", "gonial_angle_R", "chin_projection_ratio",
        "nasofacial_angle_ratio", "chin_offset_asymmetry", "texture_silicone_prob",
        "texture_pore_density", "texture_spot_density", "texture_wrinkle_forehead",
        "texture_wrinkle_nasolabial", "texture_global_smoothness", "texture_specular_gloss",
        "texture_lbp_complexity"
    ],
    # ... остальные ракурсы по аналогии
    "unclassified": [
        "cranial_face_index", "jaw_width_ratio", "gonial_angle_L", "gonial_angle_R",
        "interorbital_ratio", "orbital_asymmetry_index", "texture_silicone_prob",
        "texture_pore_density", "texture_global_smoothness", "texture_specular_gloss"
    ]
}

POSE_DISTANCE_THRESHOLD = 15.0  # градусов
EMA_ALPHA = 0.3  # коэффициент для EMA обновления
ANOMALY_THRESHOLD_MULTIPLIER = 2.5
ANOMALY_THRESHOLD_MULTIPLIER_APPROXIMATE = 3.0
CHRONOLOGY_GAP_YEARS = 2


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PhotoMetadata:
    """Метаданные фотографии, извлеченные из имени файла"""
    path: Path
    photo_id: str
    date: datetime
    yaw: float
    pitch: float
    roll: float
    bucket: str = "unclassified"
    
    @property
    def pose_vector(self) -> np.ndarray:
        return np.array([self.yaw, self.pitch, self.roll])


@dataclass
class ExtractedData:
    """Извлеченные данные для фотографии"""
    photo_id: str
    metadata: PhotoMetadata
    vertices: Optional[np.ndarray] = None
    angles: Optional[Dict[str, float]] = None
    zone_metrics: Optional[Dict[str, float]] = None
    texture_metrics: Optional[Dict[str, float]] = None
    visibility_mask: Optional[Dict[str, bool]] = None
    expression_flags: Optional[Dict[str, bool]] = None
    extraction_success: bool = False
    error_message: Optional[str] = None


@dataclass
class CalibrationPair:
    """Калибровочная пара с метаданными"""
    cal_A: str
    cal_B: str
    pose_distance_A: float
    pose_distance_B: float
    approximate_match: bool
    calibration_deltas: Dict[str, float] = field(default_factory=dict)


@dataclass
class PairResult:
    """Результат сравнения пары фото"""
    pair_id: str
    group: str
    photo_A: PhotoMetadata
    photo_B: PhotoMetadata
    calibration: CalibrationPair
    raw_metrics: Dict[str, float]
    corrected_metrics: Dict[str, float]
    calibration_quality: str
    anomaly_flags: List[Dict[str, Any]] = field(default_factory=list)
    bayesian_verdict: Optional[Dict[str, float]] = None
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())


@dataclass
class GroupCalibrationStats:
    """EMA-статистика калибровки для группы"""
    group: str
    metric_medians: Dict[str, float] = field(default_factory=dict)
    metric_stds: Dict[str, float] = field(default_factory=dict)
    sample_count: int = 0
    
    def update(self, calibration_deltas: Dict[str, float]):
        """EMA-обновление статистики"""
        for metric, value in calibration_deltas.items():
            if metric not in self.metric_medians:
                self.metric_medians[metric] = value
                self.metric_stds[metric] = 0.0
            else:
                old_median = self.metric_medians[metric]
                old_std = self.metric_stds[metric]
                
                # EMA для медианы
                new_median = (1 - EMA_ALPHA) * old_median + EMA_ALPHA * value
                
                # EMA для variance
                variance = (value - new_median) ** 2
                new_variance = (1 - EMA_ALPHA) * (old_std ** 2) + EMA_ALPHA * variance
                new_std = np.sqrt(new_variance)
                
                self.metric_medians[metric] = new_median
                self.metric_stds[metric] = new_std
        
        self.sample_count += 1
    
    def get_threshold(self, metric: str, approximate: bool = False) -> float:
        """Получить порог для детекции аномалий"""
        if metric not in self.metric_medians:
            return float('inf')
        
        multiplier = ANOMALY_THRESHOLD_MULTIPLIER_APPROXIMATE if approximate else ANOMALY_THRESHOLD_MULTIPLIER
        return abs(self.metric_medians[metric]) + multiplier * self.metric_stds[metric]


# =============================================================================
# Парсинг и подготовка данных
# =============================================================================

class MetadataParser:
    """Парсер метаданных из имен файлов"""
    
    # Регулярные выражения для извлечения углов и дат
    DATE_PATTERNS = [
        r'(\d{4})[-_](\d{2})[-_](\d{2})',  # 2023-05-15 или 2023_05_15
        r'(\d{4})(\d{2})(\d{2})',          # 20230515
    ]
    
    ANGLE_PATTERNS = [
        # Полный формат: yaw15, yaw_15, yaw-5
        r'yaw_?(-?\d+\.?\d*)',
        r'pitch_?(-?\d+\.?\d*)',
        r'roll_?(-?\d+\.?\d*)',
        # Сокращенный формат: y16, p-18, r1 (работает после подчеркивания)
        r'(?<![a-zA-Z0-9])y(-?\d+)',          # y16 или y-13
        r'(?<![a-zA-Z0-9])p(-?\d+)',          # p-18 или p17
        r'(?<![a-zA-Z0-9])r(-?\d+)',          # r1 или r-11
    ]
    
    @classmethod
    def parse_photo(cls, path: Path) -> Optional[PhotoMetadata]:
        """Парсить метаданные из имени файла"""
        filename = path.stem
        
        # Извлечение даты
        date = None
        for pattern in cls.DATE_PATTERNS:
            match = re.search(pattern, filename)
            if match:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                try:
                    date = datetime(year, month, day)
                    break
                except ValueError:
                    continue
        
        if date is None:
            # Fallback: дата модификации файла
            stat = path.stat()
            date = datetime.fromtimestamp(stat.st_mtime)
            # Не выводим warning для калибровочных фото, так как для них дата не требуется
            if not filename.startswith('calibration_') and not filename.startswith('._calibration_'):
                logger.warning(f"Не удалось извлечь дату из имени {filename}, используется mtime")
        
        # Извлечение углов (по умолчанию 0)
        yaw, pitch, roll = 0.0, 0.0, 0.0
        
        # Полный формат: yaw15, pitch-5, roll2
        for pattern in cls.ANGLE_PATTERNS[:3]:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                value = float(match.group(1))
                if 'yaw' in pattern:
                    yaw = value
                elif 'pitch' in pattern:
                    pitch = value
                elif 'roll' in pattern:
                    roll = value
        
        # Сокращенный формат: y16p-5r2 - ищем y/p/r последовательно
        # Находим y с числом
        y_match = re.search(r'(?<![a-zA-Z])y(-?\d+)', filename, re.IGNORECASE)
        if y_match and yaw == 0.0:  # только если не найдено в полном формате
            yaw = float(y_match.group(1))
        
        # Находим p с числом  
        p_match = re.search(r'(?<![a-zA-Z])p(-?\d+)', filename, re.IGNORECASE)
        if p_match and pitch == 0.0:
            pitch = float(p_match.group(1))
        
        # Находим r с числом
        r_match = re.search(r'(?<![a-zA-Z])r(-?\d+)', filename, re.IGNORECASE)
        if r_match and roll == 0.0:
            roll = float(r_match.group(1))
        
        # Определение bucket по yaw
        bucket = cls._classify_bucket(yaw)
        
        return PhotoMetadata(
            path=path,
            photo_id=path.stem,
            date=date,
            yaw=yaw,
            pitch=pitch,
            roll=roll,
            bucket=bucket
        )
    
    @staticmethod
    def _classify_bucket(yaw: float) -> str:
        """Классифицировать ракурс по yaw"""
        for bucket, (min_yaw, max_yaw) in BUCKET_THRESHOLDS.items():
            if min_yaw <= yaw <= max_yaw:
                return bucket
        return "unclassified"


class DatasetOrganizer:
    """Организатор датасета по группам ракурсов"""
    
    def __init__(self, main_path: Path, calibration_path: Path):
        self.main_path = main_path
        self.calibration_path = calibration_path
        self.main_photos: List[PhotoMetadata] = []
        self.calibration_photos: List[PhotoMetadata] = []
        self.groups: Dict[str, List[PhotoMetadata]] = defaultdict(list)
    
    def scan_and_organize(self) -> Dict[str, List[PhotoMetadata]]:
        """Сканировать и организовать фото по группам"""
        logger.info(f"Сканирование основного датасета: {self.main_path}")
        self.main_photos = self._scan_directory(self.main_path)
        
        logger.info(f"Сканирование калибровочного датасета: {self.calibration_path}")
        self.calibration_photos = self._scan_directory(self.calibration_path)
        
        # Группировка основного датасета
        for photo in self.main_photos:
            self.groups[photo.bucket].append(photo)
        
        # Сортировка внутри групп по хронологии
        for bucket in self.groups:
            self.groups[bucket].sort(key=lambda p: (p.date, p.yaw))
        
        # Логирование статистики
        total_main = len(self.main_photos)
        total_cal = len(self.calibration_photos)
        logger.info(f"Найдено фото: основной={total_main}, калибровочный={total_cal}")
        
        for bucket, photos in sorted(self.groups.items()):
            cal_count = len([p for p in self.calibration_photos if p.bucket == bucket])
            logger.info(f"  Группа {bucket}: основной={len(photos)}, калибровка={cal_count}")
        
        return dict(self.groups)
    
    def _scan_directory(self, path: Path) -> List[PhotoMetadata]:
        """Сканировать директорию и парсить метаданные"""
        photos = []
        
        if not path.exists():
            logger.error(f"Директория не существует: {path}")
            return photos
        
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG']:
            for file_path in path.rglob(ext):
                if file_path.name.startswith('.'):
                    continue
                metadata = MetadataParser.parse_photo(file_path)
                if metadata:
                    photos.append(metadata)
        
        return photos
    
    def find_calibration_match(self, target: PhotoMetadata) -> Tuple[Optional[PhotoMetadata], float, bool]:
        """Найти ближайшее калибровочное фото по углам"""
        bucket_cal = [p for p in self.calibration_photos if p.bucket == target.bucket]
        
        if not bucket_cal:
            # Fallback: любое калибровочное фото
            bucket_cal = self.calibration_photos
        
        if not bucket_cal:
            return None, float('inf'), True
        
        # Поиск ближайшего по евклидову расстоянию
        best_match = None
        best_distance = float('inf')
        
        target_pose = target.pose_vector
        for cal_photo in bucket_cal:
            distance = np.linalg.norm(target_pose - cal_photo.pose_vector)
            if distance < best_distance:
                best_distance = distance
                best_match = cal_photo
        
        approximate = best_distance > POSE_DISTANCE_THRESHOLD
        
        return best_match, best_distance, approximate


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'as_dict'):
            return obj.as_dict()
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        if hasattr(obj, 'item') and callable(obj.item):
            try:
                return obj.item()
            except Exception:
                pass
        if 'bool' in type(obj).__name__.lower():
            return bool(obj)
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


# =============================================================================
# Extract этап
# =============================================================================

class ExtractStage:
    """Этап извлечения признаков"""
    
    def __init__(self, service: ForensicWorkbenchService, storage_path: Path):
        self.service = service
        self.storage_path = storage_path
        self.reconstruction = ReconstructionAdapter()
        self.texture_analyzer = SkinTextureAnalyzer()
    
    def extract_photo(self, metadata: PhotoMetadata, is_calibration: bool = False) -> ExtractedData:
        """Извлечь данные для одной фотографии"""
        result = ExtractedData(photo_id=metadata.photo_id, metadata=metadata)
        
        try:
            # Проверка кэша
            cache_path = self._get_cache_path(metadata, is_calibration)
            if cache_path.exists():
                logger.debug(f"Использование кэша для {metadata.photo_id}")
                cached_data = self._load_from_cache(cache_path)
                if cached_data:
                    return cached_data
            
            # 3D реконструкция
            logger.info(f"Начало 3D реконструкции для {metadata.photo_id}...")
            try:
                from pathlib import Path as PathLib
                recon_result = self.reconstruction.reconstruct(PathLib(str(metadata.path)))
            except Exception as recon_err:
                logger.error(f"Ошибка реконструкции {metadata.photo_id}: {recon_err}")
                raise ValueError(f"3D реконструкция не удалась: {recon_err}")
            
            if not recon_result:
                raise ValueError("Результат реконструкции пустой (None)")
            
            # ReconstructionResult - dataclass не имеет просто vertices, а vertices_world и т.д.
            vertices = getattr(recon_result, 'vertices_world', getattr(recon_result, 'vertices_camera', None))
            if vertices is None and hasattr(recon_result, 'vertices'):
                vertices = recon_result.vertices
                
            if vertices is None:
                raise ValueError(f"Результат реконструкции не имеет vertices. Тип: {type(recon_result)}, поля: {dir(recon_result)}")

            angles = {
                'yaw': getattr(recon_result, 'yaw', metadata.yaw),
                'pitch': getattr(recon_result, 'pitch', metadata.pitch),
                'roll': getattr(recon_result, 'roll', metadata.roll)
            }
            
            # Вычисление правильных макро-метрик костей для одиночного фото
            from backend.pipeline.scoring import extract_macro_bone_metrics
            from backend.pipeline.zones import MACRO_BONE_INDICES
            angles_arr = np.array([angles.get('pitch', 0), angles.get('yaw', 0), angles.get('roll', 0)])
            zone_metrics, _ = extract_macro_bone_metrics(vertices, MACRO_BONE_INDICES, angles_arr)
            
            # Определение expression flags
            expression_flags = self._detect_expression(vertices)
            
            # Применение exclusion mask
            if expression_flags.get('jaw_open') or expression_flags.get('smile'):
                zone_metrics = apply_expression_exclusion_mask(zone_metrics, expression_flags)
            
            # Текстурный анализ
            texture_metrics = self.texture_analyzer.analyze(str(metadata.path))
            
            # Определение видимости зон
            visibility_mask = self._compute_visibility(angles, metadata.bucket)
            
            result.vertices = vertices
            result.angles = angles
            result.zone_metrics = zone_metrics
            result.texture_metrics = texture_metrics
            result.visibility_mask = visibility_mask
            result.expression_flags = expression_flags
            result.extraction_success = True
            
            # Сохранение в кэш
            self._save_to_cache(cache_path, result)
            
        except Exception as e:
            result.extraction_success = False
            result.error_message = str(e)
            logger.error(f"Ошибка извлечения для {metadata.photo_id}: {e}")
        
        return result
    
    def extract_dataset(self, photos: List[PhotoMetadata], is_calibration: bool = False) -> Dict[str, ExtractedData]:
        """Извлечь данные для набора фото"""
        results = {}
        
        desc = "Калибровочный датасет" if is_calibration else "Основной датасет"
        for photo in tqdm(photos, desc=f"Extract: {desc}"):
            extracted = self.extract_photo(photo, is_calibration)
            results[photo.photo_id] = extracted
        
        return results
    
    def _get_cache_path(self, metadata: PhotoMetadata, is_calibration: bool) -> Path:
        """Получить путь к кэшу"""
        if is_calibration:
            cache_dir = self.storage_path / "calibration" / metadata.photo_id
        else:
            cache_dir = self.storage_path / "pose" / metadata.photo_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / "photo_data.json"
    
    def _save_to_cache(self, path: Path, data: ExtractedData, is_calibration: bool = False):
        """Сохранить в кэш (photo_data.json для pose/, data.json для calibration/)"""
        cache_data = {
            "photo_id": data.photo_id,
            "path": str(data.metadata.path),
            "date": data.metadata.date.isoformat(),
            "pose": {
                "yaw": data.metadata.yaw,
                "pitch": data.metadata.pitch,
                "roll": data.metadata.roll,
                "bucket": data.metadata.bucket
            },
            "angles": data.angles,
            "zone_metrics": data.zone_metrics,
            "texture_metrics": data.texture_metrics,
            "visibility_mask": data.visibility_mask,
            "expression_flags": data.expression_flags,
            "extraction_success": data.extraction_success,
            "timestamp": datetime.now().isoformat()
        }
        
        # Сохранение vertices отдельно как numpy
        if data.vertices is not None:
            vertices_path = path.parent / "vertices.npy"
            np.save(vertices_path, data.vertices)
        
        with open(path, 'w') as f:
            json.dump(cache_data, f, cls=NumpyEncoder, indent=2, ensure_ascii=False)
    
    def _load_from_cache(self, path: Path) -> Optional[ExtractedData]:
        """Загрузить из кэша (поддержка старого и нового формата)"""
        try:
            with open(path, 'r') as f:
                cache_data = json.load(f)
            
            # Поддержка нового формата (path, pose) и старого (metadata)
            if 'path' in cache_data:
                # Новый формат (photo_data.json)
                pose = cache_data.get('pose', {})
                metadata = PhotoMetadata(
                    path=Path(cache_data['path']),
                    photo_id=cache_data['photo_id'],
                    date=datetime.fromisoformat(cache_data['date']),
                    yaw=pose.get('yaw', 0),
                    pitch=pose.get('pitch', 0),
                    roll=pose.get('roll', 0),
                    bucket=pose.get('bucket', 'unknown')
                )
            else:
                # Старый формат (data.json)
                metadata = PhotoMetadata(
                    path=Path(cache_data['metadata']['path']),
                    photo_id=cache_data['photo_id'],
                    date=datetime.fromisoformat(cache_data['metadata']['date']),
                    yaw=cache_data['metadata']['yaw'],
                    pitch=cache_data['metadata']['pitch'],
                    roll=cache_data['metadata']['roll'],
                    bucket=cache_data['metadata']['bucket']
                )
            
            result = ExtractedData(photo_id=cache_data['photo_id'], metadata=metadata)
            result.angles = cache_data.get('angles')
            result.zone_metrics = cache_data.get('zone_metrics')
            result.texture_metrics = cache_data.get('texture_metrics')
            result.visibility_mask = cache_data.get('visibility_mask')
            result.expression_flags = cache_data.get('expression_flags')
            result.extraction_success = cache_data.get('extraction_success', False)
            
            # Загрузка vertices
            vertices_path = path.parent / "vertices.npy"
            if vertices_path.exists():
                result.vertices = np.load(vertices_path)
            
            return result
            
        except Exception as e:
            logger.warning(f"Не удалось загрузить кэш {path}: {e}")
            return None
    
    def _detect_expression(self, vertices: np.ndarray) -> Dict[str, bool]:
        """Детекция выражений лица"""
        # Упрощенная реализация - в реальности использовать pipeline/expression.py
        return {"jaw_open": False, "smile": False}
    
    def _compute_visibility(self, angles: Dict[str, float], bucket: str) -> Dict[str, bool]:
        """Определение видимости зон"""
        # Упрощенная реализация
        return {zone: True for zone in ["forehead", "nose", "chin", "left_eye", "right_eye"]}


# =============================================================================
# Calibrate этап
# =============================================================================

class CalibrateStage:
    """Этап калибровочной коррекции"""
    
    def __init__(
        self,
        organizer: DatasetOrganizer,
        main_data: Dict[str, ExtractedData],
        cal_data: Dict[str, ExtractedData],
        storage_path: Path
    ):
        self.organizer = organizer
        self.main_data = main_data
        self.cal_data = cal_data
        self.storage_path = storage_path
        self.results: List[PairResult] = []
    
    def process_group(self, group_name: str, photos: List[PhotoMetadata]) -> List[PairResult]:
        """Обработать одну группу ракурсов"""
        if len(photos) < 2:
            logger.warning(f"Группа {group_name} содержит менее 2 фото, пропуск")
            return []
        
        logger.info(f"Обработка группы {group_name}: {len(photos)} фото")
        
        group_results = []
        stats = GroupCalibrationStats(group=group_name)
        current_cal_photo: Optional[str] = None
        
        for i in range(len(photos) - 1):
            photo_A = photos[i]
            photo_B = photos[i + 1]
            
            # Проверка разрыва хронологии
            time_gap = (photo_B.date - photo_A.date).days / 365.25
            if time_gap > CHRONOLOGY_GAP_YEARS:
                logger.info(f"Разрыв хронологии {time_gap:.1f} лет между {photo_A.photo_id} и {photo_B.photo_id}")
                current_cal_photo = None  # Сброс цепочки
                stats = GroupCalibrationStats(group=group_name)  # Новая статистика
            
            # Обработка пары
            result = self._process_pair(
                photo_A, photo_B,
                current_cal_photo,
                stats,
                group_name
            )
            
            if result:
                group_results.append(result)
                
                # Обновление состояния для следующей итерации
                current_cal_photo = result.calibration.cal_B
                stats.update(result.calibration.calibration_deltas)
            
            logger.debug(f"Обработана пара {i+1}/{len(photos)-1} в группе {group_name}")
        
        logger.info(f"Группа {group_name} завершена: {len(group_results)} пар")
        return group_results
    
    def _process_pair(
        self,
        photo_A: PhotoMetadata,
        photo_B: PhotoMetadata,
        prev_cal_B: Optional[str],
        stats: GroupCalibrationStats,
        group: str
    ) -> Optional[PairResult]:
        """Обработать одну пару фото с калибровкой"""
        
        # Получение извлеченных данных
        data_A = self.main_data.get(photo_A.photo_id)
        data_B = self.main_data.get(photo_B.photo_id)
        
        if not data_A or not data_B:
            logger.error(f"Отсутствуют данные для пары {photo_A.photo_id} - {photo_B.photo_id}")
            return None
        
        if not data_A.extraction_success or not data_B.extraction_success:
            logger.warning(f"Неуспешное извлечение для пары {photo_A.photo_id} - {photo_B.photo_id}")
            return None
        
        # Подбор калибровочной пары
        calibration = self._select_calibration_pair(
            photo_A, photo_B, prev_cal_B
        )
        
        if not calibration:
            logger.warning(f"Не удалось подобрать калибровку для пары {photo_A.photo_id} - {photo_B.photo_id}")
            return None
        
        # Сравнение калибровочной пары
        cal_deltas = self._compare_calibration_pair(calibration)
        calibration.calibration_deltas = cal_deltas
        
        # Канонизация и сравнение основной пары
        try:
            raw_metrics = self._compare_main_pair(data_A, data_B, group)
        except Exception as e:
            logger.error(f"Ошибка сравнения пары {photo_A.photo_id} - {photo_B.photo_id}: {e}")
            return None
        
        # Применение калибровочной коррекции
        corrected_metrics = {}
        for metric, raw_value in raw_metrics.items():
            if metric in cal_deltas:
                corrected_metrics[metric] = raw_value - cal_deltas[metric]
            else:
                corrected_metrics[metric] = raw_value
        
        # Определение качества калибровки
        calibration_quality = self._assess_calibration_quality(calibration, stats)
        
        # Детекция аномалий
        anomaly_flags = self._detect_anomalies(
            corrected_metrics, stats, calibration.approximate_match
        )
        
        # Формирование результата
        result = PairResult(
            pair_id=f"{photo_A.photo_id}__{photo_B.photo_id}",
            group=group,
            photo_A=photo_A,
            photo_B=photo_B,
            calibration=calibration,
            raw_metrics=raw_metrics,
            corrected_metrics=corrected_metrics,
            calibration_quality=calibration_quality,
            anomaly_flags=anomaly_flags
        )
        
        # Сохранение результата
        self._save_pair_result(result)
        
        return result
    
    def _select_calibration_pair(
        self,
        photo_A: PhotoMetadata,
        photo_B: PhotoMetadata,
        prev_cal_B: Optional[str]
    ) -> Optional[CalibrationPair]:
        """Подобрать калибровочную пару"""
        
        # Для photo_A используем prev_cal_B (reuse) или ищем новый
        if prev_cal_B and prev_cal_B in self.cal_data:
            cal_A_data = self.cal_data[prev_cal_B]
            cal_A = prev_cal_B
            distance_A = np.linalg.norm(
                photo_A.pose_vector - cal_A_data.metadata.pose_vector
            )
        else:
            cal_A_match, distance_A, _ = self.organizer.find_calibration_match(photo_A)
            if not cal_A_match:
                return None
            cal_A = cal_A_match.photo_id
        
        # Для photo_B всегда ищем новый
        cal_B_match, distance_B, approximate = self.organizer.find_calibration_match(photo_B)
        if not cal_B_match:
            return None
        cal_B = cal_B_match.photo_id
        
        return CalibrationPair(
            cal_A=cal_A,
            cal_B=cal_B,
            pose_distance_A=distance_A,
            pose_distance_B=distance_B,
            approximate_match=approximate
        )
    
    def _compare_calibration_pair(self, calibration: CalibrationPair) -> Dict[str, float]:
        """Сравнить калибровочную пару и получить дельты"""
        data_A = self.cal_data.get(calibration.cal_A)
        data_B = self.cal_data.get(calibration.cal_B)
        
        if not data_A or not data_B:
            return {}
        
        # Используем метрики зон как прокси для дельт
        metrics_A = data_A.zone_metrics or {}
        metrics_B = data_B.zone_metrics or {}
        
        deltas = {}
        all_metrics = set(metrics_A.keys()) | set(metrics_B.keys())
        
        for metric in all_metrics:
            val_A = metrics_A.get(metric, 0)
            val_B = metrics_B.get(metric, 0)
            if val_A is None:
                val_A = 0
            if val_B is None:
                val_B = 0
            deltas[metric] = val_A - val_B
        
        return deltas
    
    def _compare_main_pair(
        self,
        data_A: ExtractedData,
        data_B: ExtractedData,
        group: str
    ) -> Dict[str, float]:
        """Сравнить основную пару фото"""
        
        # Канонизация вершин
        vertices_A_canon = canonicalize_vertices_for_bucket(
            data_A.vertices,
            [data_A.angles.get('pitch', 0), data_A.angles.get('yaw', 0), data_A.angles.get('roll', 0)],
            group
        )
        
        vertices_B_canon = canonicalize_vertices_for_bucket(
            data_B.vertices,
            [data_B.angles.get('pitch', 0), data_B.angles.get('yaw', 0), data_B.angles.get('roll', 0)],
            group
        )
        
        # Выравнивание пары
        # Упрощенная реализация - используем метрики зон
        metrics_A = data_A.zone_metrics or {}
        metrics_B = data_B.zone_metrics or {}
        
        raw_metrics = {}
        all_metrics = set(metrics_A.keys()) | set(metrics_B.keys())
        
        for metric in all_metrics:
            val_A = metrics_A.get(metric, 0)
            val_B = metrics_B.get(metric, 0)
            if val_A is None:
                val_A = 0
            if val_B is None:
                val_B = 0
            raw_metrics[metric] = val_A - val_B
        
        return raw_metrics
    
    def _assess_calibration_quality(
        self,
        calibration: CalibrationPair,
        stats: GroupCalibrationStats
    ) -> str:
        """Оценить качество калибровки"""
        if calibration.approximate_match:
            return "low"
        
        max_distance = max(calibration.pose_distance_A, calibration.pose_distance_B)
        
        if max_distance < 5.0:
            return "high"
        elif max_distance < 10.0:
            return "medium"
        else:
            return "marginal"
    
    def _detect_anomalies(
        self,
        corrected_metrics: Dict[str, float],
        stats: GroupCalibrationStats,
        approximate: bool
    ) -> List[Dict[str, Any]]:
        """Детекция аномалий в метриках"""
        flags = []
        
        for metric, value in corrected_metrics.items():
            threshold = stats.get_threshold(metric, approximate)
            
            if abs(value) > threshold:
                severity = "danger" if abs(value) > threshold * 1.2 else "warn"
                flags.append({
                    "metric": metric,
                    "value": value,
                    "threshold": threshold,
                    "severity": severity
                })
        
        return flags
    
    def _save_pair_result(self, result: PairResult):
        """Сохранить результат пары в папки обоих фото"""
        pose_path = self.storage_path / "pose"
        pose_path.mkdir(exist_ok=True)
        
        # Сохраняем как next для photo_A
        photo_a_folder = pose_path / result.photo_A.photo_id
        photo_a_folder.mkdir(parents=True, exist_ok=True)
        
        next_file = photo_a_folder / "pair_with_next.json"
        next_data = self._pair_to_dict(result, direction="next")
        with open(next_file, 'w') as f:
            json.dump(next_data, f, cls=NumpyEncoder, indent=2, ensure_ascii=False)
        
        # Сохраняем как previous для photo_B
        photo_b_folder = pose_path / result.photo_B.photo_id
        photo_b_folder.mkdir(parents=True, exist_ok=True)
        
        prev_file = photo_b_folder / "pair_with_previous.json"
        prev_data = self._pair_to_dict(result, direction="previous")
        with open(prev_file, 'w') as f:
            json.dump(prev_data, f, cls=NumpyEncoder, indent=2, ensure_ascii=False)
        
        logger.debug(f"Пара сохранена: {result.photo_A.photo_id} <-> {result.photo_B.photo_id}")
    
    def _pair_to_dict(self, result: PairResult, direction: str) -> Dict[str, Any]:
        """Конвертировать PairResult в словарь для сохранения"""
        base = {
            "pair_id": result.pair_id,
            "direction": direction,
            "group": result.group,
            "calibration": {
                "quality": result.calibration_quality,
                "cal_A": result.calibration.cal_A,
                "cal_B": result.calibration.cal_B,
                "pose_distance_A": result.calibration.pose_distance_A,
                "pose_distance_B": result.calibration.pose_distance_B,
                "approximate_match": result.calibration.approximate_match,
                "calibration_deltas": result.calibration.calibration_deltas
            },
            "metrics": {
                "raw": result.raw_metrics,
                "corrected": result.corrected_metrics
            },
            "anomalies": result.anomaly_flags
        }
        
        if direction == "next":
            base["other_photo"] = {
                "id": result.photo_B.photo_id,
                "date": result.photo_B.date.isoformat(),
                "pose": {"yaw": result.photo_B.yaw, "pitch": result.photo_B.pitch, "roll": result.photo_B.roll}
            }
        else:  # previous
            base["other_photo"] = {
                "id": result.photo_A.photo_id,
                "date": result.photo_A.date.isoformat(),
                "pose": {"yaw": result.photo_A.yaw, "pitch": result.photo_A.pitch, "roll": result.photo_A.roll}
            }
        
        return base


# =============================================================================
# Analyze этап
# =============================================================================

class AnalyzeStage:
    """Этап хронологического анализа"""
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.results: List[PairResult] = []
    
    def load_results(self) -> List[PairResult]:
        """Загрузить все результаты пар"""
        pose_path = self.storage_path / "pose"
        results = []
        
        if not pose_path.exists():
            return []
            
        for photo_dir in pose_path.iterdir():
            if not photo_dir.is_dir():
                continue
                
            next_file = photo_dir / "pair_with_next.json"
            photo_data_file = photo_dir / "photo_data.json"
            
            if not next_file.exists():
                continue
                
            try:
                with open(next_file, 'r') as f:
                    data = json.load(f)
                
                # Загружаем метаданные для фото А из photo_data.json
                photo_A_meta = None
                if photo_data_file.exists():
                    try:
                        with open(photo_data_file, 'r') as f_meta:
                            meta_data = json.load(f_meta)
                        photo_A_meta = PhotoMetadata(
                            path=Path(meta_data.get('path', '')),
                            photo_id=meta_data['photo_id'],
                            date=datetime.fromisoformat(meta_data['date']),
                            yaw=meta_data['pose']['yaw'],
                            pitch=meta_data['pose']['pitch'],
                            roll=meta_data['pose']['roll'],
                            bucket=meta_data['pose'].get('bucket', data.get('group', 'unclassified'))
                        )
                    except Exception as meta_err:
                        logger.warning(f"Ошибка загрузки метаданных фото А в {photo_dir.name}: {meta_err}")
                
                if not photo_A_meta:
                    # Резервное восстановление метаданных фото А
                    photo_A_meta = PhotoMetadata(
                        path=Path(),
                        photo_id=photo_dir.name,
                        date=datetime.now(),
                        yaw=0.0,
                        pitch=0.0,
                        roll=0.0,
                        bucket=data.get('group', 'unclassified')
                    )
                
                # Восстановление метаданных фото B из other_photo в pair_with_next.json
                photo_B_meta = PhotoMetadata(
                    path=Path(),
                    photo_id=data['other_photo']['id'],
                    date=datetime.fromisoformat(data['other_photo']['date']),
                    yaw=data['other_photo']['pose']['yaw'],
                    pitch=data['other_photo']['pose']['pitch'],
                    roll=data['other_photo']['pose']['roll'],
                    bucket=data.get('group', 'unclassified')
                )
                
                cal_data = data['calibration']
                calibration = CalibrationPair(
                    cal_A=cal_data['cal_A'],
                    cal_B=cal_data['cal_B'],
                    pose_distance_A=cal_data['pose_distance_A'],
                    pose_distance_B=cal_data['pose_distance_B'],
                    approximate_match=cal_data['approximate_match'],
                    calibration_deltas=cal_data.get('calibration_deltas', {})
                )
                
                result = PairResult(
                    pair_id=data['pair_id'],
                    group=data['group'],
                    photo_A=photo_A_meta,
                    photo_B=photo_B_meta,
                    calibration=calibration,
                    raw_metrics=data['metrics']['raw'],
                    corrected_metrics=data['metrics']['corrected'],
                    calibration_quality=cal_data['quality'],
                    anomaly_flags=data.get('anomalies', []),
                    timestamp=data.get('timestamp', 0)
                )
                
                results.append(result)
                
            except Exception as e:
                logger.warning(f"Не удалось загрузить результаты из {next_file}: {e}")
        
        # Сортировка по дате photo_B (конец интервала)
        results.sort(key=lambda r: r.photo_B.date)
        
        self.results = results
        return results
    
    def build_chronology(self) -> Dict[str, Any]:
        """Построить хронологическую линию"""
        if not self.results:
            logger.warning("Нет результатов для построения хронологии")
            return {}
        
        logger.info(f"Построение хронологии для {len(self.results)} пар")
        
        # Группировка по группам ракурсов
        by_group = defaultdict(list)
        for result in self.results:
            by_group[result.group].append(result)
        
        chronology = {
            "total_pairs": len(self.results),
            "groups": {},
            "global_timeline": []
        }
        
        for group, group_results in by_group.items():
            group_chrono = self._analyze_group_chronology(group, group_results)
            chronology["groups"][group] = group_chrono
        
        # Глобальная временная линия (все группы вместе)
        chronology["global_timeline"] = self._build_global_timeline(self.results)
        
        return chronology
    
    def _analyze_group_chronology(self, group: str, results: List[PairResult]) -> Dict[str, Any]:
        """Анализ хронологии для одной группы"""
        
        # Сортировка по дате
        results.sort(key=lambda r: r.photo_B.date)
        
        timeline = []
        anomalies = []
        
        prev_date = None
        prev_metrics = None
        
        for result in results:
            entry = {
                "date": result.photo_B.date.isoformat(),
                "photo_A": result.photo_A.photo_id,
                "photo_B": result.photo_B.photo_id,
                "corrected_metrics": result.corrected_metrics,
                "calibration_quality": result.calibration_quality,
                "anomaly_flags": result.anomaly_flags
            }
            
            timeline.append(entry)
            
            # Детекция скачков
            if prev_metrics is not None:
                for metric, value in result.corrected_metrics.items():
                    if metric not in prev_metrics:
                        continue
                    
                    prev_value = prev_metrics[metric]
                    delta = abs(value - prev_value)
                    
                    # Порог для костных метрик (жесткие структуры)
                    if "jaw" in metric or "cranial" in metric or "orbit" in metric:
                        if delta > 0.15:
                            anomalies.append({
                                "type": "bone_jump",
                                "metric": metric,
                                "delta": delta,
                                "from_photo": result.photo_A.photo_id,
                                "to_photo": result.photo_B.photo_id,
                                "severity": "danger" if delta > 0.25 else "warn"
                            })
                    
                    # Проверка инверсии асимметрии
                    if "asymmetry" in metric:
                        if (prev_value > 0 and value < 0) or (prev_value < 0 and value > 0):
                            anomalies.append({
                                "type": "asymmetry_inversion",
                                "metric": metric,
                                "from_value": prev_value,
                                "to_value": value,
                                "from_photo": result.photo_A.photo_id,
                                "to_photo": result.photo_B.photo_id,
                                "severity": "danger"
                            })
            
            prev_date = result.photo_B.date
            prev_metrics = result.corrected_metrics.copy()
        
        return {
            "group": group,
            "pair_count": len(results),
            "timeline": timeline,
            "anomalies": anomalies,
            "anomaly_count": len(anomalies)
        }
    
    def _build_global_timeline(self, results: List[PairResult]) -> List[Dict[str, Any]]:
        """Построить глобальную временную линию"""
        # Сортировка по дате
        results.sort(key=lambda r: r.photo_B.date)
        
        timeline = []
        for result in results:
            timeline.append({
                "date": result.photo_B.date.isoformat(),
                "group": result.group,
                "photo_A": result.photo_A.photo_id,
                "photo_B": result.photo_B.photo_id,
                "anomaly_count": len(result.anomaly_flags),
                "calibration_quality": result.calibration_quality
            })
        
        return timeline
    
    def generate_report(self) -> Dict[str, Any]:
        """Сгенерировать итоговый отчет"""
        chronology = self.build_chronology()
        
        # Подсчет статистики
        total_anomalies = sum(
            g.get("anomaly_count", 0)
            for g in chronology.get("groups", {}).values()
        )
        
        calibration_quality_dist = defaultdict(int)
        for result in self.results:
            calibration_quality_dist[result.calibration_quality] += 1
        
        report = {
            "summary": {
                "total_pairs_processed": len(self.results),
                "total_groups": len(chronology.get("groups", {})),
                "total_anomalies_detected": total_anomalies,
                "calibration_quality_distribution": dict(calibration_quality_dist)
            },
            "chronology": chronology,
            "recommendations": self._generate_recommendations(chronology)
        }
        
        return report
    
    def _generate_recommendations(self, chronology: Dict[str, Any]) -> List[str]:
        """Сгенерировать рекомендации"""
        recommendations = []
        
        # Анализ качества калибровки
        low_cal_count = sum(
            1 for r in self.results if r.calibration_quality == "low"
        )
        if low_cal_count > len(self.results) * 0.1:
            recommendations.append(
                f"Высокий процент низкокачественной калибровки ({low_cal_count}/{len(self.results)}). "
                "Рекомендуется пополнить калибровочный датасет для проблемных ракурсов."
            )
        
        # Анализ аномалий
        for group, group_data in chronology.get("groups", {}).items():
            anomalies = group_data.get("anomalies", [])
            if len(anomalies) > group_data.get("pair_count", 0) * 0.05:
                recommendations.append(
                    f"Группа {group}: высокая частота аномалий ({len(anomalies)}). "
                    "Требуется дополнительный анализ или проверка качества исходных данных."
                )
        
        return recommendations
    
    def save_report(self, report: Dict[str, Any], output_path: Path):
        """Сохранить отчет"""
        with open(output_path, 'w') as f:
            json.dump(report, f, cls=NumpyEncoder, indent=2, ensure_ascii=False)
        
        logger.info(f"Отчет сохранен: {output_path}")
    
    def save_chronology_index(self, report: Dict[str, Any], output_path: Path):
        """Сохранить индекс хронологии для навигации в интерфейсе"""
        chronology = report.get("chronology", {})
        
        # Построение индекса: photo_id -> [prev_photo, next_photo]
        photo_index = {}
        
        for group_name, group_data in chronology.get("groups", {}).items():
            timeline = group_data.get("timeline", [])
            for i, entry in enumerate(timeline):
                photo_id = entry.get("photo_id")
                if not photo_id:
                    continue
                
                prev_photo = timeline[i-1].get("photo_id") if i > 0 else None
                next_photo = timeline[i+1].get("photo_id") if i < len(timeline) - 1 else None
                
                photo_index[photo_id] = {
                    "group": group_name,
                    "date": entry.get("date"),
                    "prev": prev_photo,
                    "next": next_photo,
                    "anomaly_count": entry.get("anomaly_count", 0)
                }
        
        index = {
            "groups": {
                name: [e.get("photo_id") for e in data.get("timeline", []) if e.get("photo_id")]
                for name, data in chronology.get("groups", {}).items()
            },
            "global_timeline": [
                {
                    "photo_id": entry.get("photo_id"),
                    "date": entry.get("date"),
                    "group": entry.get("group")
                }
                for entry in chronology.get("global_timeline", [])
            ],
            "photo_index": photo_index,
            "summary": report.get("summary", {})
        }
        
        with open(output_path, 'w') as f:
            json.dump(index, f, cls=NumpyEncoder, indent=2, ensure_ascii=False)
        
        logger.info(f"Индекс хронологии сохранен: {output_path}")


# =============================================================================
# Ad-hoc режим сравнения
# =============================================================================

class AdHocComparator:
    """Ad-hoc сравнение двух фото"""
    
    def __init__(
        self,
        organizer: DatasetOrganizer,
        main_data: Dict[str, ExtractedData],
        cal_data: Dict[str, ExtractedData]
    ):
        self.organizer = organizer
        self.main_data = main_data
        self.cal_data = cal_data
    
    def compare(
        self,
        photo_A_id: str,
        photo_B_id: str,
        photo_A_path: Optional[Path] = None,
        photo_B_path: Optional[Path] = None
    ) -> Optional[PairResult]:
        """Сравнить две фото ad-hoc"""
        
        # Загрузка или извлечение данных
        data_A = self._get_or_extract(photo_A_id, photo_A_path)
        data_B = self._get_or_extract(photo_B_id, photo_B_path)
        
        if not data_A or not data_B:
            logger.error("Не удалось получить данные для одной или обеих фото")
            return None
        
        # Определение группы по yaw
        avg_yaw = (data_A.metadata.yaw + data_B.metadata.yaw) / 2
        group = MetadataParser._classify_bucket(avg_yaw)
        
        # Подбор калибровочной пары
        cal_A_match, distance_A, _ = self.organizer.find_calibration_match(data_A.metadata)
        cal_B_match, distance_B, approximate = self.organizer.find_calibration_match(data_B.metadata)
        
        if not cal_A_match or not cal_B_match:
            logger.error("Не удалось подобрать калибровочную пару")
            return None
        
        calibration = CalibrationPair(
            cal_A=cal_A_match.photo_id,
            cal_B=cal_B_match.photo_id,
            pose_distance_A=distance_A,
            pose_distance_B=distance_B,
            approximate_match=approximate
        )
        
        # Сравнение калибровочной пары
        cal_deltas = self._compare_calibration_pair(calibration)
        calibration.calibration_deltas = cal_deltas
        
        # Сравнение основной пары (упрощенная логика)
        raw_metrics = {}
        for metric in set(data_A.zone_metrics or {}) | set(data_B.zone_metrics or {}):
            val_A = (data_A.zone_metrics or {}).get(metric, 0)
            val_B = (data_B.zone_metrics or {}).get(metric, 0)
            if val_A is None:
                val_A = 0
            if val_B is None:
                val_B = 0
            raw_metrics[metric] = val_A - val_B
        
        # Корректировка
        corrected_metrics = {}
        for metric, raw_value in raw_metrics.items():
            if metric in cal_deltas:
                corrected_metrics[metric] = raw_value - cal_deltas[metric]
            else:
                corrected_metrics[metric] = raw_value
        
        # Оценка качества
        calibration_quality = "high"
        if approximate:
            calibration_quality = "low"
        elif max(distance_A, distance_B) > 10:
            calibration_quality = "marginal"
        
        return PairResult(
            pair_id=f"{photo_A_id}__{photo_B_id}",
            group=group,
            photo_A=data_A.metadata,
            photo_B=data_B.metadata,
            calibration=calibration,
            raw_metrics=raw_metrics,
            corrected_metrics=corrected_metrics,
            calibration_quality=calibration_quality
        )
    
    def _get_or_extract(self, photo_id: str, photo_path: Optional[Path]) -> Optional[ExtractedData]:
        """Получить данные из кэша или извлечь"""
        if photo_id in self.main_data:
            return self.main_data[photo_id]
        
        if photo_path and photo_path.exists():
            # Извлечение on-the-fly
            metadata = MetadataParser.parse_photo(photo_path)
            if metadata:
                metadata.photo_id = photo_id
                # Используем extract stage для извлечения
                # Упрощенно: создаем mock данные
                return ExtractedData(
                    photo_id=photo_id,
                    metadata=metadata,
                    extraction_success=True,
                    zone_metrics={},
                    texture_metrics={}
                )
        
        return None
    
    def _compare_calibration_pair(self, calibration: CalibrationPair) -> Dict[str, float]:
        """Сравнить калибровочную пару"""
        data_A = self.cal_data.get(calibration.cal_A)
        data_B = self.cal_data.get(calibration.cal_B)
        
        if not data_A or not data_B:
            return {}
        
        deltas = {}
        for metric in set(data_A.zone_metrics or {}) | set(data_B.zone_metrics or {}):
            val_A = (data_A.zone_metrics or {}).get(metric, 0)
            val_B = (data_B.zone_metrics or {}).get(metric, 0)
            deltas[metric] = val_A - val_B
        
        return deltas


# =============================================================================
# Основной pipeline
# =============================================================================

class SCAPPipeline:
    """Основной класс pipeline"""
    
    def __init__(
        self,
        main_dataset_path: str,
        calibration_dataset_path: str,
        storage_path: str
    ):
        self.main_path = Path(main_dataset_path)
        self.cal_path = Path(calibration_dataset_path)
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Создание подпапок
        (self.storage_path / "pose").mkdir(exist_ok=True)        # данные по хронологии
        (self.storage_path / "comparisons").mkdir(exist_ok=True) # ad-hoc сравнения
        
        self.organizer = DatasetOrganizer(self.main_path, self.cal_path)
        self.service = ForensicWorkbenchService(
            dataset_path=str(self.main_path),
            case_name="pipeline2"
        )
        
        self.main_data: Dict[str, ExtractedData] = {}
        self.cal_data: Dict[str, ExtractedData] = {}
    
    def run_extract(self) -> Tuple[Dict[str, ExtractedData], Dict[str, ExtractedData]]:
        """Запустить этап Extract"""
        logger.info("=" * 60)
        logger.info("ЭТАП 1: EXTRACT (Извлечение признаков)")
        logger.info("=" * 60)
        
        # Сканирование и организация
        groups = self.organizer.scan_and_organize()
        
        # Извлечение данных
        extract_stage = ExtractStage(self.service, self.storage_path)
        
        self.main_data = extract_stage.extract_dataset(
            self.organizer.main_photos,
            is_calibration=False
        )
        
        self.cal_data = extract_stage.extract_dataset(
            self.organizer.calibration_photos,
            is_calibration=True
        )
        
        # Статистика
        success_main = sum(1 for d in self.main_data.values() if d.extraction_success)
        success_cal = sum(1 for d in self.cal_data.values() if d.extraction_success)
        
        logger.info(f"Extract завершен: основной={success_main}/{len(self.main_data)}, калибровка={success_cal}/{len(self.cal_data)}")
        
        return self.main_data, self.cal_data
    
    def run_calibrate(self, parallel: bool = False) -> List[PairResult]:
        """Запустить этап Calibrate"""
        logger.info("=" * 60)
        logger.info("ЭТАП 2: CALIBRATE (Калибровочная коррекция)")
        logger.info("=" * 60)
        
        if not self.main_data or not self.cal_data:
            logger.error("Отсутствуют извлеченные данные. Сначала запустите run_extract()")
            return []
        
        calibrate_stage = CalibrateStage(
            self.organizer,
            self.main_data,
            self.cal_data,
            self.storage_path
        )
        
        # Получение групп
        groups = self.organizer.scan_and_organize()
        
        all_results = []
        
        if parallel and len(groups) > 1:
            # Параллельная обработка групп
            with ProcessPoolExecutor() as executor:
                futures = {
                    executor.submit(calibrate_stage.process_group, group, photos): group
                    for group, photos in groups.items()
                }
                
                for future in as_completed(futures):
                    group = futures[future]
                    try:
                        results = future.result()
                        all_results.extend(results)
                        logger.info(f"Группа {group} завершена: {len(results)} пар")
                    except Exception as e:
                        logger.error(f"Ошибка в группе {group}: {e}")
        else:
            # Последовательная обработка
            for group, photos in tqdm(groups.items(), desc="Обработка групп"):
                results = calibrate_stage.process_group(group, photos)
                all_results.extend(results)
        
        logger.info(f"Calibrate завершен: {len(all_results)} пар обработано")
        
        return all_results
    
    def run_analyze(self) -> Dict[str, Any]:
        """Запустить этап Analyze"""
        logger.info("=" * 60)
        logger.info("ЭТАП 3: ANALYZE (Хронологический анализ)")
        logger.info("=" * 60)
        
        analyze_stage = AnalyzeStage(self.storage_path)
        analyze_stage.load_results()
        
        report = analyze_stage.generate_report()
        
        # Сохранение индекса хронологии
        index_path = self.storage_path / "pose" / "chronology_index.json"
        analyze_stage.save_chronology_index(report, index_path)
        
        logger.info("Analyze завершен")
        
        return report
    
    def run_full_pipeline(self) -> Dict[str, Any]:
        """Запустить полный pipeline"""
        self.run_extract()
        self.run_calibrate()
        report = self.run_analyze()
        
        logger.info("=" * 60)
        logger.info("ПОЛНЫЙ PIPELINE ЗАВЕРШЕН")
        logger.info("=" * 60)
        
        return report
    
    def compare_ad_hoc(
        self,
        photo_a_path: str,
        photo_b_path: str
    ) -> Optional[PairResult]:
        """Ad-hoc сравнение двух фото с детальным отчетом.
        
        Args:
            photo_a_path: путь к первому файлу (например, 'photo1.jpg')
            photo_b_path: путь ко второму файлу (например, 'photo2.jpg')
        """
        path_a = Path(photo_a_path)
        path_b = Path(photo_b_path)
        
        if not path_a.exists():
            logger.error(f"Файл не найден: {path_a}")
            return None
        if not path_b.exists():
            logger.error(f"Файл не найден: {path_b}")
            return None
        
        # Создаем отдельную папку для этого сравнения
        folder_name = f"{path_a.stem}_{path_b.stem}"
        comp_folder = self.storage_path / "comparisons" / folder_name
        comp_folder.mkdir(parents=True, exist_ok=True)
        
        # Извлечение данных on-the-fly
        logger.info(f"Извлечение данных для {path_a.name}...")
        data_a = self._extract_single(path_a)
        
        logger.info(f"Извлечение данных для {path_b.name}...")
        data_b = self._extract_single(path_b)
        
        if not data_a or not data_b:
            logger.error("Не удалось извлечь данные для одного или обоих фото")
            return None
        
        # Подбор калибровочных пар
        cal_a_match, dist_a, _ = self.organizer.find_calibration_match(data_a.metadata)
        cal_b_match, dist_b, approximate = self.organizer.find_calibration_match(data_b.metadata)
        
        if not cal_a_match or not cal_b_match:
            logger.error("Не удалось подобрать калибровочные пары")
            return None
        
        # Загрузка калибровочных данных
        cal_a_data = self.cal_data.get(cal_a_match.photo_id)
        cal_b_data = self.cal_data.get(cal_b_match.photo_id)
        
        if not cal_a_data or not cal_b_data:
            logger.error("Калибровочные данные не найдены в кэше")
            return None
        
        # Определение качества калибровки
        cal_quality = "low" if approximate else ("high" if max(dist_a, dist_b) < 5 else "medium")
        
        # Вычисление калибровочных дельт
        cal_deltas = {}
        for metric in set(cal_a_data.zone_metrics or {}) | set(cal_b_data.zone_metrics or {}):
            val_a = (cal_a_data.zone_metrics or {}).get(metric, 0)
            val_b = (cal_b_data.zone_metrics or {}).get(metric, 0)
            if val_a is None:
                val_a = 0
            if val_b is None:
                val_b = 0
            cal_deltas[metric] = val_a - val_b
        
        # Вычисление метрик основной пары
        raw_metrics = {}
        for metric in set(data_a.zone_metrics or {}) | set(data_b.zone_metrics or {}):
            val_a = (data_a.zone_metrics or {}).get(metric, 0)
            val_b = (data_b.zone_metrics or {}).get(metric, 0)
            if val_a is None:
                val_a = 0
            if val_b is None:
                val_b = 0
            raw_metrics[metric] = val_a - val_b
        
        # Применение калибровки
        corrected_metrics = {}
        for metric, raw_val in raw_metrics.items():
            corrected_metrics[metric] = raw_val - cal_deltas.get(metric, 0)
        
        # Детекция аномалий
        anomalies = []
        for metric, value in corrected_metrics.items():
            if abs(value) > 0.15:  # порог
                severity = "danger" if abs(value) > 0.25 else "warn"
                anomalies.append({"metric": metric, "value": value, "severity": severity})
        
        # Формирование результата
        result = PairResult(
            pair_id=f"{path_a.stem}_{path_b.stem}",
            group=data_a.metadata.bucket if data_a.metadata.bucket == data_b.metadata.bucket else "mixed",
            photo_A=data_a.metadata,
            photo_B=data_b.metadata,
            calibration=CalibrationPair(
                cal_A=cal_a_match.photo_id,
                cal_B=cal_b_match.photo_id,
                pose_distance_A=dist_a,
                pose_distance_B=dist_b,
                approximate_match=approximate,
                calibration_deltas=cal_deltas
            ),
            raw_metrics=raw_metrics,
            corrected_metrics=corrected_metrics,
            calibration_quality=cal_quality,
            anomaly_flags=anomalies
        )
        
        # Сохранение отчета
        self._save_comparison_result(result, comp_folder)
        
        return result
    
    def _extract_single(self, path: Path) -> Optional[ExtractedData]:
        """Извлечь данные для одного файла"""
        # Парсинг метаданных из имени файла
        metadata = MetadataParser.parse_photo(path)
        if not metadata:
            logger.error(f"Не удалось распарсить метаданные: {path}")
            return None
        
        # Проверка кэша
        cache_dir = self.storage_path / "main" / metadata.photo_id
        cache_file = cache_dir / "data.json"
        
        if cache_file.exists():
            logger.info(f"Использование кэша для {path.name}")
            # Загрузка из кэша
            try:
                with open(cache_file, 'r') as f:
                    cache_data = json.load(f)
                
                data = ExtractedData(
                    photo_id=metadata.photo_id,
                    metadata=metadata,
                    extraction_success=True
                )
                data.angles = cache_data.get('angles')
                data.zone_metrics = cache_data.get('zone_metrics')
                data.texture_metrics = cache_data.get('texture_metrics')
                
                vertices_path = cache_file.parent / "vertices.npy"
                if vertices_path.exists():
                    data.vertices = np.load(vertices_path)
                
                return data
            except Exception as e:
                logger.warning(f"Не удалось загрузить кэш: {e}")
        
        # Извлечение через backend
        try:
            from backend.pipeline.reconstruction import ReconstructionAdapter
            from backend.pipeline.zones import compute_zone_metrics
            from backend.pipeline.texture import SkinTextureAnalyzer
            
            recon = ReconstructionAdapter()
            recon_result = recon.resolve_reconstruction(str(path))
            
            if not recon_result or 'vertices' not in recon_result:
                raise ValueError("Реконструкция не удалась")
            
            vertices = recon_result['vertices']
            angles = recon_result.get('angles', {
                'yaw': metadata.yaw,
                'pitch': metadata.pitch,
                'roll': metadata.roll
            })
            from backend.pipeline.scoring import extract_macro_bone_metrics
            from backend.pipeline.zones import MACRO_BONE_INDICES
            angles_arr = np.array([angles.get('pitch', 0), angles.get('yaw', 0), angles.get('roll', 0)])
            zone_metrics, _ = extract_macro_bone_metrics(vertices, MACRO_BONE_INDICES, angles_arr)
            texture_metrics = SkinTextureAnalyzer().analyze(str(path))
            
            data = ExtractedData(
                photo_id=metadata.photo_id,
                metadata=metadata,
                vertices=vertices,
                angles=angles,
                zone_metrics=zone_metrics,
                texture_metrics=texture_metrics,
                extraction_success=True
            )
            
            # Сохранение в кэш
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_data = {
                'photo_id': metadata.photo_id,
                'metadata': {
                    'path': str(path),
                    'date': metadata.date.isoformat(),
                    'yaw': metadata.yaw,
                    'pitch': metadata.pitch,
                    'roll': metadata.roll,
                    'bucket': metadata.bucket
                },
                'angles': angles,
                'zone_metrics': zone_metrics,
                'texture_metrics': texture_metrics,
                'extraction_success': True
            }
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, cls=NumpyEncoder, indent=2)
            
            if vertices is not None:
                np.save(cache_dir / "vertices.npy", vertices)
            
            return data
            
        except Exception as e:
            logger.error(f"Ошибка извлечения {path}: {e}")
            return None
    
    def _save_comparison_result(self, result: PairResult, comp_folder: Path):
        """Сохранить результат ad-hoc сравнения в папку сравнения"""
        report_file = comp_folder / "comparison_report.json"
        
        report = {
            "comparison_id": comparison_id,
            "timestamp": datetime.now().isoformat(),
            "photo_A": {
                "id": result.photo_A.photo_id,
                "date": result.photo_A.date.isoformat(),
                "pose": {"yaw": result.photo_A.yaw, "pitch": result.photo_A.pitch, "roll": result.photo_A.roll}
            },
            "photo_B": {
                "id": result.photo_B.photo_id,
                "date": result.photo_B.date.isoformat(),
                "pose": {"yaw": result.photo_B.yaw, "pitch": result.photo_B.pitch, "roll": result.photo_B.roll}
            },
            "calibration": {
                "quality": result.calibration_quality,
                "cal_A": result.calibration.cal_A,
                "cal_B": result.calibration.cal_B,
                "pose_distance_A": result.calibration.pose_distance_A,
                "pose_distance_B": result.calibration.pose_distance_B,
                "calibration_deltas": result.calibration.calibration_deltas
            },
            "metrics": {
                "corrected": result.corrected_metrics,
                "raw": result.raw_metrics,
                "delta_applied": {k: result.raw_metrics.get(k, 0) - result.corrected_metrics.get(k, 0) 
                                 for k in result.raw_metrics.keys()}
            },
            "anomalies": result.anomaly_flags,
            "summary": {
                "assessment": "anomaly" if any(f.get("severity") == "danger" for f in result.anomaly_flags) 
                             else ("suspicious" if result.anomaly_flags else "stable"),
                "anomaly_count": len(result.anomaly_flags)
            }
        }
        
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, cls=NumpyEncoder, indent=2, ensure_ascii=False)
        
        logger.info(f"Отчет сохранен: {report_file}")
        logger.info(f"Результаты сравнения в папке: {comp_folder}")


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DEEPUTIN Forensic Pipeline v2.0 (SCAP)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Режимы работы:
  full          - Полный pipeline (Extract → Calibrate → Analyze)
  extract       - Только извлечение признаков
  calibrate     - Только калибровочная коррекция (требуется extract)
  analyze       - Только хронологический анализ (требуется calibrate)
  compare       - Ad-hoc сравнение двух фото

Примеры:
  # Полный pipeline
  python pipeline2.py --mode full --dataset /Volumes/SDCARD/photo/all
  
  # Ad-hoc сравнение двух файлов
  python pipeline2.py --mode compare --photo_a /path/to/photo1.jpg --photo_b /path/to/photo2.jpg
        """
    )
    
    parser.add_argument("--mode", required=True,
                       choices=["full", "extract", "calibrate", "analyze", "compare"],
                       help="Режим работы pipeline")
    parser.add_argument("--dataset", default="/Volumes/SDCARD/photo/all",
                       help="Путь к основному датасету")
    parser.add_argument("--calibration", default="/Volumes/SDCARD/photo/calibration",
                       help="Путь к калибровочному датасету")
    parser.add_argument("--storage", default="/Volumes/SDCARD/storage/pipeline2",
                       help="Путь для сохранения результатов (default: /Volumes/SDCARD/storage/pipeline2)")
    parser.add_argument("--photo_a", help="Путь к фото A для режима compare (например, photo1.jpg)")
    parser.add_argument("--photo_b", help="Путь к фото B для режима compare (например, photo2.jpg)")
    parser.add_argument("--parallel", action="store_true",
                       help="Параллельная обработка групп (только для calibrate)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Подробный вывод логов")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Инициализация pipeline
    pipeline = SCAPPipeline(
        main_dataset_path=args.dataset,
        calibration_dataset_path=args.calibration,
        storage_path=args.storage
    )
    
    # Выполнение по режиму
    if args.mode == "full":
        report = pipeline.run_full_pipeline()
        print(f"\n{'='*60}")
        print("ИТОГОВЫЙ ОТЧЕТ")
        print(f"{'='*60}")
        print(f"Обработано пар: {report['summary']['total_pairs_processed']}")
        print(f"Групп ракурсов: {report['summary']['total_groups']}")
        print(f"Аномалий найдено: {report['summary']['total_anomalies_detected']}")
        print(f"\nКачество калибровки:")
        for quality, count in report['summary']['calibration_quality_distribution'].items():
            print(f"  {quality}: {count}")
        print(f"\nРекомендации:")
        for rec in report['recommendations']:
            print(f"  - {rec}")
    
    elif args.mode == "extract":
        pipeline.run_extract()
    
    elif args.mode == "calibrate":
        pipeline.run_calibrate(parallel=args.parallel)
    
    elif args.mode == "analyze":
        report = pipeline.run_analyze()
        print(json.dumps(report['summary'], indent=2, ensure_ascii=False))
    
    elif args.mode == "compare":
        if not args.photo_a or not args.photo_b:
            parser.error("Для режима compare требуются --photo_a и --photo_b (пути к файлам)")
        
        result = pipeline.compare_ad_hoc(
            args.photo_a,  # путь к файлу A
            args.photo_b   # путь к файлу B
        )
        
        if result:
            print(f"\n{'='*60}")
            print(f"РЕЗУЛЬТАТ СРАВНЕНИЯ: {result.photo_A.photo_id} vs {result.photo_B.photo_id}")
            print(f"{'='*60}")
            print(f"Группа: {result.group}")
            print(f"Качество калибровки: {result.calibration_quality}")
            print(f"\nКалибровочная пара:")
            print(f"  cal_A: {result.calibration.cal_A} (dist: {result.calibration.pose_distance_A:.2f})")
            print(f"  cal_B: {result.calibration.cal_B} (dist: {result.calibration.pose_distance_B:.2f})")
            print(f"  approximate: {result.calibration.approximate_match}")
            print(f"\nКлючевые метрики (corrected):")
            for metric, value in list(result.corrected_metrics.items())[:10]:
                print(f"  {metric}: {value:.4f}")
            if result.anomaly_flags:
                print(f"\nАномалии:")
                for flag in result.anomaly_flags:
                    print(f"  [!] {flag['metric']}: {flag['value']:.4f} ({flag['severity']})")
        else:
            print("Ошибка: не удалось выполнить сравнение")


if __name__ == "__main__":
    main()
