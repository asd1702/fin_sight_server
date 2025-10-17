"""
관측치(core) JSONL 내보내기 스크립트

이 스크립트는 DB에 적재된 관측치(observations)를 읽어 `data/observations_core15.jsonl`
형식으로 재생성합니다. 주로 백업, 재배포, 또는 다른 환경으로 시드 재생성 용도로 사용합니다.

기본 동작:
    - 카탈로그(`data/catalog_core15.json`)에 있는 지표들만 내보냅니다(파일이 없으면 전체 내보냄).
    - `--only` 옵션으로 특정 indicator_id 목록만 내보낼 수 있습니다.
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
    """카탈로그 파일에서 indicator_id 집합을 로드합니다.

    반환값: 카탈로그에 정의된 indicator_id의 집합. 파일이 없거나 읽기 실패 시 빈 집합을 반환합니다.
    """
    # 카탈로그 파일이 없으면 전체 내보내기로 간주
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
    """DB에서 내보낼 indicator_id를 순회합니다.

    필터링 규칙:
      - `only`가 주어지면 해당 집합에 포함된 id만 처리
      - `from_catalog`가 비어있지 않으면 카탈로그에 존재하는 id만 처리
    """
    # DB에서 모든 indicator_id를 조회한 뒤, 필요하면 필터링 적용
    q = session.query(Indicator.indicator_id)
    for (iid,) in q.all():
        if only and iid not in only:
            continue
        if from_catalog and iid not in from_catalog:
            continue
        yield iid


def export(core_only: bool, only_ids: Set[str]):
    """관측치를 JSONL로 내보냅니다.

    파라미터:
      - core_only: True이면 카탈로그 기준 필터 적용(단, 카탈로그 파일이 없으면 전체)
      - only_ids: 특정 id 집합만 내보내려면 전달
    """
    # DB 세션 열기 및 카탈로그 로드
    session = SessionLocal()
    catalog_ids = load_catalog_ids()
    exported = 0
    # 출력 파일에 JSONL 형식으로 기록
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        for iid in iter_indicator_ids(session, only_ids, catalog_ids):
            obs = session.query(Observation).filter(Observation.indicator_id == iid).order_by(Observation.date).all()
            if not obs:
                # 저장된 관측치가 없으면 건너뜀
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
