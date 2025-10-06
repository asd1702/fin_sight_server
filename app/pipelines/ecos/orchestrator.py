from __future__ import annotations
"""Ingestion orchestrator (MVP)."""
from datetime import date, timedelta
from typing import Optional
import logging
import os
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.statistic_model.statistic import Indicator, Observation
from app.models.statistic_model.ingestion_meta import IndicatorState, IngestionRun
from app.pipelines.ecos.api_client import EcosApiClient, IndicatorSpec
from app.pipelines.ecos.validator import validate_records
from app.pipelines.ecos.transformer import normalize
from app.pipelines.ecos.loader import upsert_observations, update_indicator_state

logger = logging.getLogger(__name__)

DEFAULT_INITIAL_DATE = date(2000, 1, 1)


def _bootstrap_state_if_missing(session: Session, indicator_id: str) -> bool:
    """If indicator_state row missing but observations already exist, create it.
    Returns True if bootstrapped."""
    state = session.get(IndicatorState, indicator_id)
    if state is not None:
        return False
    max_min = session.execute(
        select(func.max(Observation.date), func.count(Observation.date))
        .where(Observation.indicator_id == indicator_id)
    ).one()
    max_date, cnt = max_min
    if cnt and max_date:
        session.add(IndicatorState(indicator_id=indicator_id, last_loaded_date=max_date, total_rows=cnt))
        return True
    return False


def run_incremental(session: Session, recheck_days: int = 7, initial_date: date = DEFAULT_INITIAL_DATE) -> str:
    run = IngestionRun()
    session.add(run)
    session.flush()  # get run_id
    # Try passing API key explicitly for clarity
    ecos_key = os.getenv('ECOS_API_KEY')
    if not ecos_key:
        try:
            from app.core.config import settings  # type: ignore
            ecos_key = getattr(settings, 'ECOS_API_KEY', None)
        except Exception:
            ecos_key = None
    api = EcosApiClient(api_key=ecos_key)

    stmt = select(Indicator)
    indicators = session.scalars(stmt).all()

    total_inserted = 0
    total_skipped = 0
    errors = 0

    today = date.today()
    cutoff_end = today - timedelta(days=1)

    for ind in indicators:
        try:
            state: Optional[IndicatorState] = session.get(IndicatorState, ind.indicator_id)
            logical_start = (state.last_loaded_date + timedelta(days=1)) if (state and state.last_loaded_date) else initial_date
            rewind_start = today - timedelta(days=recheck_days)
            start_date = min(logical_start, rewind_start)
            if start_date > cutoff_end:
                logger.debug("Skip %s (start_date %s > cutoff_end %s)", ind.indicator_id, start_date, cutoff_end)
                continue
            spec = IndicatorSpec(
                indicator_id=ind.indicator_id,
                stat_code=ind.stat_code,
                item_code1=ind.item_code1,
                item_code2=ind.item_code2,
                item_code3=ind.item_code3,
                item_code4=ind.item_code4,
                frequency=ind.frequency,
            )
            raw = api.fetch_observations(spec, start=start_date, end=cutoff_end)
            valid, rejected = validate_records(raw)
            normalized = normalize(valid)
            inserted, _ = upsert_observations(session, normalized)
            update_indicator_state(session, ind.indicator_id, [r["date"] for r in normalized])
            # If nothing inserted AND state missing but old data exists, bootstrap
            if inserted == 0:
                boot = _bootstrap_state_if_missing(session, ind.indicator_id)
                if boot:
                    logger.info("Bootstrapped state for %s from existing observations", ind.indicator_id)
            logger.info(
                "Indicator %s fetched=%d valid=%d inserted=%d rejected=%d start=%s end=%s",
                ind.indicator_id, len(raw), len(valid), inserted, rejected, start_date, cutoff_end
            )
            total_inserted += inserted
            total_skipped += rejected
        except Exception as e:
            errors += 1
            logger.exception("Indicator %s failed: %s", ind.indicator_id, e)

    run.rows_inserted = total_inserted
    run.rows_skipped = total_skipped
    run.error_count = errors
    run.status = 'SUCCESS' if errors == 0 else ('PARTIAL' if total_inserted > 0 else 'FAILED')
    run.incremental_from = None  # Could be min of start dates processed
    run.incremental_to = cutoff_end
    return str(run.run_id)
