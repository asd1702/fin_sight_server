"""Export core indicator observations to JSONL (observations_core15.jsonl).

This replicates the original seeding file so you can regenerate it from the DB
after running incremental ingestion. By default exports all indicators whose
indicator_id ends with one of (.d, .m, .q, .y) and are in the catalog file
catalog_core15.json (if present). You can also pass --only to restrict.
"""
from __future__ import annotations
import os
import sys
import json
import argparse
from datetime import date
from typing import Set, Iterable

from pathlib import Path
PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.database import SessionLocal
from app.models.statistic_model.statistic import Observation, Indicator
from logs.logging_config import get_logger

logger = get_logger(__name__)

DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
CATALOG_FILE = os.path.join(DATA_DIR, 'catalog_core15.json')
OUTPUT_FILE = os.path.join(DATA_DIR, 'observations_core15.jsonl')


def load_catalog_ids() -> Set[str]:
    if not os.path.exists(CATALOG_FILE):
        logger.warning("Catalog file %s not found; exporting all indicators", CATALOG_FILE)
        return set()
    try:
        with open(CATALOG_FILE, 'r', encoding='utf-8') as f:
            catalog = json.load(f)
        return {c['indicator_id'] for c in catalog if 'indicator_id' in c}
    except Exception as e:
        logger.error("Failed reading catalog: %s", e)
        return set()


def iter_indicator_ids(session, only: Set[str], from_catalog: Set[str]) -> Iterable[str]:
    q = session.query(Indicator.indicator_id)
    for (iid,) in q.all():
        if only and iid not in only:
            continue
        if from_catalog and iid not in from_catalog:
            continue
        yield iid


def export(core_only: bool, only_ids: Set[str]):
    session = SessionLocal()
    catalog_ids = load_catalog_ids()
    exported = 0
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        for iid in iter_indicator_ids(session, only_ids, catalog_ids):
            obs = session.query(Observation).filter(Observation.indicator_id == iid).order_by(Observation.date).all()
            if not obs:
                continue
            for row in obs:
                out.write(json.dumps({
                    'indicator_id': row.indicator_id,
                    'date': row.date.isoformat(),
                    'value': row.value,
                }, ensure_ascii=False) + '\n')
            exported += len(obs)
            logger.info("Exported %s rows for %s", len(obs), iid)
    logger.info("Export complete. Total rows=%s -> %s", exported, OUTPUT_FILE)
    session.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', nargs='*', help='Specific indicator_ids to export')
    ap.add_argument('--all', action='store_true', help='Ignore catalog_core15.json and export all indicators')
    args = ap.parse_args()
    only_ids = set(args.only or [])
    export(core_only=not args.all, only_ids=only_ids)


if __name__ == '__main__':
    main()
