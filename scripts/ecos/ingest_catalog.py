from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import List, Dict, Any

import os
import sys
from sqlalchemy.orm import Session

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.models.statistic_model.statistic import Indicator
from app.models.statistic_model.ingestion_meta import IndicatorState

try:
    from logs.logging_config import get_logger
except ModuleNotFoundError:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    def get_logger(name):
        return logging.getLogger(name)

logger = get_logger(__name__)


def load_catalog(path: Path) -> List[Dict[str, Any]]:
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Catalog JSON must be a list of indicator objects")
    return data


def upsert_indicators(session: Session, rows: List[Dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        # Mandatory fields check
        if not row.get('indicator_id') or not row.get('name'):
            logger.warning("Skipping invalid row missing indicator_id or name: %s", row)
            continue
        indicator = Indicator(
            indicator_id=row['indicator_id'],
            name=row['name'],
            frequency=row.get('frequency'),
            unit=row.get('unit'),
            source=row.get('source'),
            notes=row.get('notes'),
            stat_code=row.get('stat_code'),
            item_code1=row.get('item_code1'),
            item_code2=row.get('item_code2'),
            item_code3=row.get('item_code3'),
            item_code4=row.get('item_code4'),
        )
        session.merge(indicator)
        count += 1
    return count


def bootstrap_state(session: Session, rows: List[Dict[str, Any]], force: bool=False) -> int:
    created = 0
    for row in rows:
        ind_id = row.get('indicator_id')
        if not ind_id:
            continue
        exists = session.get(IndicatorState, ind_id)
        if exists and not force:
            continue
        if exists and force:
            session.delete(exists)
            session.flush()
        session.add(IndicatorState(indicator_id=ind_id, last_loaded_date=None, total_rows=0))
        created += 1
    return created


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', default='data/catalog_core15.json', help='Path to catalog JSON file')
    parser.add_argument('--bootstrap-state', action='store_true', help='Create missing indicator_state rows')
    parser.add_argument('--force-state', action='store_true', help='Recreate indicator_state rows even if they exist')
    args = parser.parse_args()

    path = Path(args.file)
    logger.info("Loading catalog from %s", path)
    rows = load_catalog(path)

    session = SessionLocal()
    try:
        inserted = upsert_indicators(session, rows)
        logger.info("Upserted %d indicators", inserted)
        if args.bootstrap_state:
            created = bootstrap_state(session, rows, force=args.force_state)
            logger.info("Bootstrapped %d indicator_state rows", created)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception("Catalog ingestion failed: %s", e)
        raise SystemExit(1)
    finally:
        session.close()
    logger.info("Done.")


if __name__ == '__main__':
    main()
