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


"""
카탈로그 JSON을 읽어 indicators 테이블에 upsert하고(선택적으로) indicator_state를 초기화하는 스크립트.

주요 옵션:
  --file <path>         : 카탈로그 JSON 경로 (기본: data/catalog_core15.json)
  --bootstrap-state     : state 레코드가 없는 지표에 대해 indicator_state 생성
  --force-state         : 기존 state가 있어도 재생성 (주의: 이후 전체 재수집 유발 가능)
"""


def load_catalog(path: Path) -> List[Dict[str, Any]]:
    """카탈로그 JSON을 로드하고 목록 형태로 반환합니다.

    예외:
      - JSON 루트가 리스트가 아니면 ValueError 발생
    """
    # 파일을 열어 JSON 로드
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Catalog JSON must be a list of indicator objects")
    return data


def upsert_indicators(session: Session, rows: List[Dict[str, Any]]) -> int:
    """Indicator 객체들을 DB에 upsert 합니다.

    간단한 유효성 체크(필수 필드: indicator_id, name)를 수행하고, 이상한 행은 스킵합니다.
    반환값: 처리한 행의 수
    """
    count = 0
    for row in rows:
        # 각 행에 대해 필수 필드 검사: indicator_id, name 없으면 스킵
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
        # SQLAlchemy merge 사용: 존재하면 업데이트, 없으면 insert
        session.merge(indicator)
        count += 1
    return count


def bootstrap_state(session: Session, rows: List[Dict[str, Any]], force: bool=False) -> int:
    """indicator_state 테이블에 누락된 레코드를 생성합니다.

    파라미터:
      - force: 기존 레코드가 있더라도 삭제 후 재생성합니다(위험할 수 있음).
    반환값: 생성한 레코드 수
    """
    created = 0
    for row in rows:
        ind_id = row.get('indicator_id')
        if not ind_id:
            # indicator_id가 없으면 무시
            continue
        exists = session.get(IndicatorState, ind_id)
        if exists and not force:
            # 이미 존재하고 강제옵션이 없으면 넘어감
            continue
        if exists and force:
            # force=True 이면 기존 state 삭제 후 재생성
            session.delete(exists)
            session.flush()
        # 새 state 레코드 생성 (last_loaded_date=None으로 초기화)
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
