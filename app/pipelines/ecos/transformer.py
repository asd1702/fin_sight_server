from __future__ import annotations
"""Transformer for normalized observation records (MVP)."""
from typing import Iterable, List, Dict
from datetime import date

def normalize(records: Iterable) -> List[Dict]:
    # MVP: pass-through; hook for unit scaling, freq alignment
    out: List[Dict] = []
    for r in records:
        out.append({
            "indicator_id": r.indicator_id,
            "date": r.date,
            "value": r.value,
        })
    return out
