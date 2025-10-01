#!/usr/bin/env python3
"""Generic sector/key_word newsletter pipeline runner.

Usage:
  python3 scripts/letter/run_sector.py --sector macro --key us_economy
  python3 scripts/letter/run_sector.py --sector market --key us_market --size 15

Features:
  - sectors.yaml 기반으로 queries / prompt_key / size / min_articles 로드
  - (sector, key_word) 배치 재사용 (미완료 시)
  - 기사 수집 + 크롤링: app.core.news_letter.articles.prepare_articles
  - LLM outline 생성: processors.build_column_outline_with_llm (topic=prompt_key fallback)
  - 결과 JSON 저장: data/letters/<sector>_<key>_<ts>.json

Assumptions:
  - sector/key_word 에 대응하는 prompt_key 가 prompts.yaml 에 없으면 fallback 'company'
  - settings.LETTER_MIN_ARTICLES 전역 값 사용 (섹터별 override 를 sectors.yaml 에서 min_articles로 가능)

Future extension hooks:
  - 추가 source adapter
  - outline schema versioning
  - metric export
"""
from __future__ import annotations
import os
import sys
import yaml
import json
import argparse
from datetime import datetime, timezone
from typing import Any
from dotenv import load_dotenv

# NOTE: settings/BaseSettings validation requires all env vars present.
# We support --env to point to a specific file and load it before importing settings.

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_THIS_DIR))  # .../fin_sight_server
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from logs.logging_config import get_logger

logger = get_logger(__name__)

SECTORS_FILE = os.path.join(_THIS_DIR, 'sectors.yaml')


def load_sectors_config() -> dict[str, Any]:
    if not os.path.isfile(SECTORS_FILE):
        raise FileNotFoundError(f"sectors.yaml 파일을 찾을 수 없습니다: {SECTORS_FILE}")
    with open(SECTORS_FILE, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("sectors.yaml 최상위 구조는 dict 여야 합니다.")
    return data


def _slugify(s: str) -> str:
    return (
        s.strip().lower()
        .replace(' ', '_')
        .replace('/', '_')
    )


def run_sector(sector: str, key_word: str, size: int | None, language: str, country: str, fresh: bool) -> str | None:
    # Lazy imports AFTER env loaded
    from app.database import SessionLocal  # type: ignore
    from app.core.config import settings  # type: ignore
    from app.core.news_letter import articles as article_mod  # type: ignore
    from app.core.news_letter import processors as proc  # type: ignore
    from app.models.news_letter import LetterOutline, LetterItem  # type: ignore
    cfg = load_sectors_config()
    entry = None
    dynamic_company = False
    if sector in cfg and key_word in (cfg[sector] or {}):
        entry = cfg[sector][key_word] or {}
    elif sector == 'company':
        # 동적 company 처리: sectors.yaml 없이도 실행 가능
        dynamic_company = True
        entry = {
            'queries': [key_word],  # 필요시 원문 명칭 추가 가능
            'prompt_key': 'company',
            'size': 12,
        }
        logger.info(f"동적 company 실행 (key={key_word}) - sectors.yaml 미정의, 기본 설정 사용")
    else:
        logger.error(f"정의되지 않은 (sector,key)=({sector},{key_word}) 입니다.")
        return None

    queries = entry.get('queries') or [key_word]
    prompt_key = entry.get('prompt_key') or (key_word if not dynamic_company else 'company')
    default_size = entry.get('size') or 12
    min_articles_override = entry.get('min_articles')

    target_size = size or default_size
    db = SessionLocal()
    try:
        batch, arts = article_mod.prepare_articles(
            db=db,
            sector=sector,
            batch_key=key_word,
            queries=queries,
            target_size=target_size,
            language=language,
            country=country,
            fresh=fresh,
        )
        # 배치에 이미 outline 이 존재한다면: (1) fresh 인 경우 새 배치 강제 생성, (2) 아니면 그대로 반환
        from app.models.news_letter import LetterOutline as _LO  # local import
        existing_outline = db.query(_LO).filter(_LO.batch_id == batch.id).one_or_none()
        if existing_outline:
            if fresh:
                # 새 배치 생성 후 기사 재사용(이미 수집된 usable 기사만 복사) 대신 전체 다시 수집 로직 호출
                new_batch = article_mod.ensure_batch(db, sector=sector, batch_key=key_word, fresh=True)  # type: ignore
                batch = new_batch
                # 다시 기사 준비
                batch, arts = article_mod.prepare_articles(
                    db=db,
                    sector=sector,
                    batch_key=key_word,
                    queries=queries,
                    target_size=target_size,
                    language=language,
                    country=country,
                    fresh=True,
                )
            else:
                logger.info(f"이미 outline 존재 (batch_id={batch.id}) - 재생성 생략. --fresh 로 새로 생성 가능")
                return f"batch:{batch.id}"  # 기존 것 유지
        min_required = min_articles_override or settings.LETTER_MIN_ARTICLES
        if len(arts) < min_required:
            logger.error(f"유효 기사 부족: {len(arts)} < {min_required}")
            return None
        outline = proc.build_column_outline_with_llm(
            db=db,
            company=key_word,   # company 필드 재사용 (출력 JSON spec 유지)
            articles=arts,
            topic=prompt_key,
            model=settings.LETTER_LLM_MODEL,
        )
        if not outline:
            logger.error("LLM outline 생성 실패")
            return None
        lo = LetterOutline(
            batch_id=batch.id,
            outline=outline,
            status='completed',
            outline_version=1,
            prompt_key=prompt_key,
        )
        db.add(lo)
        for item in db.query(LetterItem).filter(LetterItem.batch_id == batch.id, LetterItem.crawl_status == "CRAWLED"):
            item.expires_at = None
        db.commit()

        logger.info(f"섹터 파이프라인 완료: (sector={sector}, key={key_word}, batch_id={batch.id}) DB 저장")
        return f"batch:{batch.id}"
    finally:
        db.close()


def _print_list(cfg: dict[str, Any]):
    print("사용 가능 (sector, key) 목록:\n")
    for sector, keys in cfg.items():
        for k, v in (keys or {}).items():
            pk = (v or {}).get('prompt_key') or k
            sz = (v or {}).get('size') or '-'
            print(f"  {sector:10s} {k:20s} prompt_key={pk:15s} size={sz}")

def _print_sector_detail(cfg: dict[str, Any], sector: str):
    if sector not in cfg:
        print(f"지정 섹터가 없습니다: {sector}")
        return
    print(f"섹터 '{sector}' 상세 구성:\n")
    for k, v in (cfg[sector] or {}).items():
        v = v or {}
        print(f"- key: {k}")
        print(f"  prompt_key: {v.get('prompt_key') or k}")
        if v.get('queries'):
            print(f"  queries: {', '.join(v['queries'])}")
        if v.get('size'):
            print(f"  default size: {v.get('size')}")
        if v.get('min_articles'):
            print(f"  min_articles: {v.get('min_articles')}")
        print()

def main():
    epilog = (
        "Examples:\n"
        "  python scripts/letter/run_sector.py --list\n"
        "  python scripts/letter/run_sector.py --show-config macro\n"
        "  python scripts/letter/run_sector.py --sector macro --key us_economy\n"
        "  python scripts/letter/run_sector.py --sector market --key us_market --size 18\n"
        "  # Dynamic company (no sectors.yaml entry required)\n"
        "  python scripts/letter/run_sector.py --sector company --key nvidia\n"
        "  # Force regeneration with new batch\n"
        "  python scripts/letter/run_sector.py --sector company --key nvidia --fresh\n"
        "\nNotes:\n"
        "  --fresh : ignores any existing incomplete batch and creates a new batch.\n"
        "  Existing outline + no --fresh -> skips LLM call and returns existing batch id.\n"
        "  Output string 'batch:<id>' indicates persisted outline in DB (letters.outlines).\n"
    )
    parser = argparse.ArgumentParser(
        description="섹터/키(또는 동적 company) 기반 뉴스레터 outline 생성 파이프라인",
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--sector', help='섹터 이름 (예: macro, market, tech, company)')
    parser.add_argument('--key', help='섹터 내 key_word 식별자 (예: us_economy, us_market, ai_industry)')
    parser.add_argument('--size', type=int, help='수집 목표 기사 수 (섹터 기본값 override)')
    parser.add_argument('--language', type=str, default='en')
    parser.add_argument('--country', type=str, default='us')
    parser.add_argument('--fresh', action='store_true', help='미완료 배치 재사용하지 않고 새로 생성')
    parser.add_argument('--list', action='store_true', help='sectors.yaml 내 모든 (sector,key) 목록 출력 후 종료')
    parser.add_argument('--show-config', metavar='SECTOR', help='특정 섹터의 key 상세 구성 출력 후 종료')
    parser.add_argument('--env', metavar='ENV_FILE', help='명시적 환경파일(.env 경로) 지정')
    args = parser.parse_args()

    # Config 로드 한번만
    cfg = load_sectors_config()

    # Load .env early (explicit override first)
    if args.env:
        if not os.path.isfile(args.env):
            print(f"--env 파일을 찾을 수 없습니다: {args.env}")
            return
        # dotenv는 명시 파일 우선 로드, 이후 기본 .env 도 추가 로드 가능
        load_dotenv(args.env, override=True)
    else:
        # fallback: project root .env
        candidate = os.path.join(_PROJECT_ROOT, '.env')
        if os.path.isfile(candidate):
            load_dotenv(candidate, override=False)

    if args.list:
        _print_list(cfg)
        return
    if args.show_config:
        _print_sector_detail(cfg, args.show_config)
        return

    if not args.sector or not args.key:
        parser.error('--sector 와 --key 를 지정하거나, --list / --show-config 를 사용하세요.')

    path = run_sector(
        sector=args.sector,
        key_word=args.key,
        size=args.size,
        language=args.language,
        country=args.country,
        fresh=args.fresh,
    )
    if path:
        print(path)
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
