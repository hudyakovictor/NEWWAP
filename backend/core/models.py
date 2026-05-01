from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


DatasetName = Literal["main", "calibration"]


class ExtractJobRequest(BaseModel):
    dataset: DatasetName = "main"
    limit: int = Field(default=24, ge=1, le=10_000)
    only_ids: list[str] | None = None
    force: bool = False


class RecomputeMetricsRequest(BaseModel):
    dataset: DatasetName = "main"
    metric_keys: list[str] = Field(default_factory=list)
    only_ids: list[str] | None = None


class CalibrationOverrideRequest(BaseModel):
    photo_id: str
    calibration_photo_id: str
    reason: str = ""
    author: str = "system"

