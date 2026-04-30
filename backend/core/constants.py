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
IMPOSSIBLE_SHORTENING_DAYS = 30

# --- Texture & Silicone ---
SILICONE_SIGMOID_BIAS = -1.8
RELIABILITY_MIN = 0.1
RELIABILITY_MAX = 1.0

# --- Bayesian & Calibration ---
SNR_UNCERTAIN_THRESHOLD = 1.0
SNR_SIGNAL_THRESHOLD = 2.0
MIN_SUCCESSFUL_PAIRS_FOR_CALIBRATION = 10
PRIOR_SAME_PERSON = 0.5

# --- Artifact Versioning ---
ARTIFACT_VERSION = "2.1.0"
RUNTIME_CONFIG_HASH_VERSION = "v2"

# --- Exclusion Lists ---
# List of photo IDs or zone names to be excluded from automated forensic analysis
EXCLUDED_FROM_ANALYSIS = [
    "main-2012_05_07-a1b2c3d4", # Example: problematic lighting
]
