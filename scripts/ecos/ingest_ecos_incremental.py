"""
ECOS 증분 수집 CLI 진입점

이 스크립트는 ECOS 파이프라인의 증분 수집을 실행하기 위한 간단한 CLI 엔트리포인트입니다.

주요 옵션:
    --recheck-days N   : 최근 N일 구간을 다시 검증(rewind)하여 값 보정 (기본: 환경변수 ECOS_RECHECK_DAYS 또는 7)
    --initial-date D   : 최초 수집 시작일 (기본: 환경변수 ECOS_INITIAL_DATE 또는 '2000-01-01')

사용 예:
    python scripts/ecos/ingest_ecos_incremental.py --recheck-days 7

주의:
    - 실제 수집 로직은 `app.pipelines.ecos.orchestrator.run_incremental`에 위임됩니다.
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

    # initial_date 파싱 (YYYY-MM-DD 형식 예상)
    from datetime import date
    initial_parts = [int(p) for p in args.initial_date.split('-')]
    initial_date = date(*initial_parts)

    # DB 세션 생성 및 파이프라인 실행
    session = SessionLocal()
    try:
        # 실제 수집 처리는 run_incremental 내부에서 수행되며, run_id(실행 식별자)를 반환
        run_id = run_incremental(session, recheck_days=args.recheck_days, initial_date=initial_date)
        session.commit()
        logger.info("Ingestion run completed: %s", run_id)
    except Exception:
        # 실패 시 롤백 후 예외를 상위로 전달 (프로세스 종료)
        session.rollback()
        logger.exception("Ingestion run failed")
        raise SystemExit(1)
    finally:
        session.close()


if __name__ == '__main__':
    main()
