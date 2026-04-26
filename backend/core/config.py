from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


def _read_localxpose_token(path: Path) -> str | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None
    if "TOKEN=" in raw:
        return raw.split("TOKEN=", 1)[1].strip() or None
    return raw


from .constants import BLUR_THRESHOLD_DEFAULT, NOISE_THRESHOLD_DEFAULT, REFERENCE_PERIOD_END, MIN_ZONE_VERTICES

@dataclass(frozen=True)
class Settings:
    repo_root: Path
    newapp_root: Path
    storage_root: Path
    main_photos_dir: Path
    calibration_dir: Path
    localxpose_env: Path
    host: str = "127.0.0.1"
    port: int = 8011
    blur_threshold: float = BLUR_THRESHOLD_DEFAULT
    noise_threshold: float = NOISE_THRESHOLD_DEFAULT
    reference_year_end: int = 2001 # TODO: Derive from REFERENCE_PERIOD_END if needed
    min_zone_vertices: int = MIN_ZONE_VERTICES
    default_extract_limit: int = 24
    max_recommendations: int = 60
    localxpose_token: str | None = None


def build_settings() -> Settings:
    repo_root = Path(__file__).resolve().parents[3]
    newapp_root = repo_root / "newapp"
    storage_root = newapp_root / "storage"
    localxpose_env = repo_root / "localxpose.env"
    return Settings(
        repo_root=repo_root,
        newapp_root=newapp_root,
        storage_root=storage_root,
        main_photos_dir=repo_root / "rebucketed_photos" / "all",
        calibration_dir=repo_root / "myface",
        localxpose_env=localxpose_env,
        localxpose_token=_read_localxpose_token(localxpose_env),
    )


SETTINGS = build_settings()

