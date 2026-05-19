from __future__ import annotations
from pathlib import Path

# --- Quality Thresholds ---
BLUR_THRESHOLD_DEFAULT = 65.0
NOISE_THRESHOLD_DEFAULT = 2.5

# --- Visibility & Z-Buffer ---
VISIBILITY_ANGLE_DEG = 82.0
Z_TOLERANCE_RATIO = 0.005 # 0.5% of Z-span
MIN_ZONE_VERTICES = 80

# --- Geometry & Scoring ---
ALIGNMENT_MIN_RANK = 3
TRIMMED_KEEP_RATIO = 0.90
MIN_KEEP_N = 50
FACE_SCALE_Y_FACTOR = 0.7

# --- Chronology (Gate-0) ---
REFERENCE_PERIOD_END = "2001-12-31"
RTR_RATIO = 0.75
RTR_MIN_ABS_DELTA = 0.15
IMPOSSIBLE_AGE_REVERSAL_DAYS = 180

# Chronology Flag Types as Constants
CHRONO_FLAG_IMPOSSIBLE = "impossible_short"
CHRONO_FLAG_RETURN = "return"
CHRONO_FLAG_TRANSITION = "transition"

# --- Texture & Silicone ---
# SILICONE_SIGMOID_BIAS: Shift parameter for synthetic/silicone probability sigmoid.
# Set to -1.8 based on empirical calibration against 3D-mask and real skin LBP distributions
# to minimize false positives under normal lighting while maintaining high sensitivity to masks.
SILICONE_SIGMOID_BIAS = -1.8
RELIABILITY_MIN = 0.1
RELIABILITY_MAX = 1.0

# --- Bayesian & Calibration ---
SNR_UNCERTAIN_THRESHOLD = 1.0
SNR_SIGNAL_THRESHOLD = 2.0
MIN_SUCCESSFUL_PAIRS_FOR_CALIBRATION = 30
MIN_PAIRS_PER_BUCKET_FOR_CALIBRATION = 5
PRIOR_SAME_PERSON = 0.65
PRIOR_IDENTITY_SWAP = 0.02

# --- Artifact Versioning ---
ARTIFACT_VERSION = "2.1.0"
RUNTIME_CONFIG_HASH_VERSION = "v2"

# --- Exclusion Lists ---
# List of photo IDs or zone names to be excluded from automated forensic analysis
EXCLUDED_FROM_ANALYSIS = [
    "main-2012_05_07-a1b2c3d4", # Example: problematic lighting
]


# --- Zone Weights ---
# Веса зон по реальным ключам из BUCKET_METRIC_KEYS.
# Приоритет на неизменные костные структуры согласно ТЗ.
# [FIX-1] Расширено до полного набора 21 зоны с анатомически обоснованными весами.
ZONE_WEIGHTS = {
    # === Костные структуры (максимальный приоритет, вес 1.0) ===
    # Эти зоны формируются в раннем возрасте и не меняются на протяжении жизни
    "nose_projection_ratio": 1.0,   # Проекция носа (переносица) — костная основа
    "orbit_depth_L_ratio": 1.0,     # Глубина левой глазницы — костная структура
    "orbit_depth_R_ratio": 1.0,     # Глубина правой глазницы — костная структура
    "jaw_width_ratio": 0.95,        # Ширина челюсти — костная структура
    "cranial_face_index": 0.95,     # Краниальный индекс — соотношение черепа и лица

    # === Костно-связочные зоны (высокий приоритет, вес 0.8-0.9) ===
    "chin_projection_ratio": 0.9,   # Проекция подбородка
    "gonial_angle_L": 0.85,         # Угол нижней челюсти L — гониальный угол
    "gonial_angle_R": 0.85,         # Угол нижней челюсти R
    "canthal_tilt_L": 0.8,          # Кантальный угол L — связочная структура
    "canthal_tilt_R": 0.8,          # Кантальный угол R
    "nasofacial_angle_ratio": 0.8,  # Угол носа к лицу

    # === Зоны симметрии и асимметрии (средний приоритет, вес 0.7) ===
    # Используются для выявления структурных несоответствий
    "chin_offset_asymmetry": 0.7,   # Асимметрия подбородка
    "nasal_frontal_index": 0.7,     # Индекс переносицы
    "forehead_slope_index": 0.7,    # Угол наклона лба

    # === Мягкие ткани и текстура (низкий приоритет, вес 0.2-0.4) ===
    # Подвержены временным изменениям, но полезны для детекции синтетики
    "texture_silicone_prob": 0.3,   # Вероятность силикона (мягкие ткани)
    "texture_pore_density": 0.25,     # Плотность пор — биологический маркер
    "nose_width_ratio": 0.25,       # Ширина носа (включает мягкие ткани крыльев)
    "texture_wrinkle_forehead": 0.2, # Морщины лба — возрастной маркер
    "texture_wrinkle_nasolabial": 0.2, # Носогубные складки
    "texture_spot_density": 0.2,    # Плотность пигментных пятен
    "texture_global_smoothness": 0.15, # Общая гладкость (инверсия пор)
    "interorbital_ratio": 0.15,     # Межглазничное расстояние (менее стабильно)
}
