from __future__ import annotations
"""Loader: bulk upsert observations + update indicator_state (MVP)."""
from typing import List, Dict, Tuple
from datetime import date
from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.statistic_model.statistic import Observation
from app.models.statistic_model.ingestion_meta import IndicatorState


def upsert_observations(session: Session, rows: List[Dict]) -> Tuple[int, int]:
    if not rows:
        return 0, 0
    # Use PostgreSQL ON CONFLICT DO UPDATE to allow value change tracking
    stmt = pg_insert(Observation).values(rows)
    update_cols = {"value": stmt.excluded.value}
    stmt = stmt.on_conflict_do_update(
        index_elements=[Observation.indicator_id, Observation.date],
        set_=update_cols,
    )
    result = session.execute(stmt)
    # Rowcount counts attempted rows, can't separate insert / update easily without returning
    return len(rows), 0


def update_indicator_state(session: Session, indicator_id: str, new_dates: List[date]) -> None:
    if not new_dates:
        return
    last_date = max(new_dates)
    state = session.get(IndicatorState, indicator_id)
    if state is None:
        state = IndicatorState(indicator_id=indicator_id, last_loaded_date=last_date, total_rows=len(new_dates))
        session.add(state)
    else:
        state.last_loaded_date = max(filter(None, [state.last_loaded_date, last_date]))
        state.total_rows = (state.total_rows or 0) + len(new_dates)
