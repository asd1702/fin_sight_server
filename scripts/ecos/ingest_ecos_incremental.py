"""CLI entry for ECOS incremental ingestion.

Usage (after folder restructuring):
    python scripts/ecos/_ingest_ecos_incremental.py --recheck-days 7
or if you prefer keeping name:
    python scripts/ecos/ingest_ecos_incremental.py --recheck-days 7
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path

# Ensure project root (two levels up: scripts/ecos -> project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal  # type: ignore
from app.pipelines.ecos.orchestrator import run_incremental  # type: ignore

try:
    from logs.logging_config import get_logger  # type: ignore
except ModuleNotFoundError:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    def get_logger(name):  # type: ignore
        return logging.getLogger(name)

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--recheck-days', type=int, default=int(os.getenv('ECOS_RECHECK_DAYS', '7')))
    parser.add_argument('--initial-date', type=str, default=os.getenv('ECOS_INITIAL_DATE', '2000-01-01'))
    args = parser.parse_args()

    from datetime import date
    initial_parts = [int(p) for p in args.initial_date.split('-')]
    initial_date = date(*initial_parts)

    session = SessionLocal()
    try:
        run_id = run_incremental(session, recheck_days=args.recheck_days, initial_date=initial_date)
        session.commit()
        logger.info("Ingestion run completed: %s", run_id)
    except Exception:
        session.rollback()
        logger.exception("Ingestion run failed")
        raise SystemExit(1)
    finally:
        session.close()


if __name__ == '__main__':
    main()
