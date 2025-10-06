from __future__ import annotations
"""Validation layer for ECOS observations (MVP)."""
from pydantic import BaseModel, field_validator
from datetime import date
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)


class ObservationIn(BaseModel):
    indicator_id: str
    date: date
    value: float

    @field_validator("value")
    @classmethod
    def value_not_null(cls, v):
        if v is None:
            raise ValueError("value is null")
        return float(v)


def validate_records(raw: List[dict]) -> Tuple[List[ObservationIn], int]:
    valid: List[ObservationIn] = []
    rejected = 0
    for r in raw:
        try:
            valid.append(ObservationIn(**r))
        except Exception as e:
            rejected += 1
            logger.debug("Reject row %s reason=%s", r, e)
    return valid, rejected
