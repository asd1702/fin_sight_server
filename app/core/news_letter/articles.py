"""Unified article preparation utilities for sector pipelines.

Provides:
  - ensure_batch: get or create (sector,key_word) LetterBatch (optionally fresh)
  - collect_and_crawl: fetch metadata from API, create LetterItems, crawl contents
  - backfill_from_cache: reuse recent crawled items for same (sector,key_word)
  - prepare_articles: high-level orchestrator returning (batch, articles_list)

This mirrors logic previously embedded in letter_pipeline.py so that run_sector.py
can operate generically without duplicating ingestion code.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple

from sqlalchemy.orm import Session

from logs.logging_config import get_logger
from app.core.config import settings
from app.models.news_letter import LetterBatch, LetterItem
from . import collectors

logger = get_logger(__name__)


def ensure_batch(db: Session, sector: str, key_word: str, fresh: bool) -> LetterBatch:
    key_word_norm = key_word.strip().lower().replace(' ', '_')
    batch: LetterBatch | None = None
    if not fresh:
        batch = (
            db.query(LetterBatch)
            .filter(LetterBatch.sector == sector, LetterBatch.key_word == key_word_norm)
            .order_by(LetterBatch.created_at.desc())
            .first()
        )
    if batch is None:
        batch = LetterBatch(sector=sector, key_word=key_word_norm)
        db.add(batch)
        db.commit()
        db.refresh(batch)
        logger.info(f"새 배치 생성: (sector={sector}, key_word={key_word_norm}, id={batch.id})")
    return batch


def _api_fill(db: Session, batch: LetterBatch, queries: List[str], target_size: int, language: str, country: str) -> int:
    # 간단히 첫 query 만 사용하거나, 여러 query 순회 누적
    created = 0
    expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.LETTER_TTL_HOURS)
    per_query_size = max(1, target_size // max(1, len(queries)))
    for q in queries:
        if created >= target_size:
            break
        remaining = target_size - created
        size = min(per_query_size, remaining)
        api_items = collectors.call_news_data_api(query=[q], size=size, language=language, country=country)
        for it in api_items:
            if created >= target_size:
                break
            url = it.get('url') or it.get('link')
            if not url:
                continue
            try:
                url = str(url)
            except Exception:
                continue
            item = LetterItem(
                batch_id=batch.id,
                title=it.get('title'),
                url=url,
                description=it.get('description'),
                published_at=None,
                content=None,
                crawl_status="PENDING",
                expires_at=expires_at,
            )
            try:
                db.add(item)
                db.commit()
                db.refresh(item)
                created += 1
            except Exception as e:
                db.rollback()
                logger.debug(f"아이템 생성 실패 url={url}: {e}")
                continue
    if created:
        logger.info(f"API 메타 삽입: {created}개")
    return created


def backfill_from_cache(db: Session, batch: LetterBatch, target_size: int) -> int:
    min_len = settings.LETTER_MIN_CONTENT_LEN
    existing_urls = {u for (u,) in db.query(LetterItem.url).filter(LetterItem.batch_id == batch.id).all() if u}
    current_count = db.query(LetterItem).filter(LetterItem.batch_id == batch.id).count()
    added = 0
    max_age_days = getattr(settings, 'LETTER_CACHE_MAX_AGE_DAYS', 14)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    q = (
        db.query(LetterItem)
        .join(LetterBatch, LetterItem.batch_id == LetterBatch.id)
        .filter(
            LetterBatch.sector == batch.sector,
            LetterBatch.key_word == batch.key_word,
            LetterItem.crawl_status == "CRAWLED",
            LetterItem.content.isnot(None),
            LetterItem.created_at >= cutoff,
            LetterItem.batch_id != batch.id,
        )
        .order_by(LetterItem.created_at.desc())
        .limit(max(target_size * 3, target_size))
    )
    for it in q:
        if current_count + added >= target_size:
            break
        if not it.url or it.url in existing_urls:
            continue
        content = it.content or ""
        if len(content) < min_len:
            continue
        try:
            clone = LetterItem(
                batch_id=batch.id,
                title=it.title,
                url=str(it.url),
                description=it.description,
                published_at=it.published_at,
                content=content,
                crawl_status="CRAWLED",
                expires_at=None,
            )
            db.add(clone)
            db.commit()
            db.refresh(clone)
            existing_urls.add(clone.url)
            added += 1
        except Exception:
            db.rollback()
            continue
    if added:
        logger.info(f"캐시 재활용: {added}개")
    return added


def _crawl_pending(db: Session, batch: LetterBatch) -> int:
    max_attempts = settings.LETTER_MAX_CRAWL_ATTEMPTS
    min_len = settings.LETTER_MIN_CONTENT_LEN
    success = 0
    for item in db.query(LetterItem).filter(LetterItem.batch_id == batch.id):
        if item.crawl_status == "CRAWLED" and item.content and len(item.content) >= min_len:
            continue
        ok = False
        for _ in range(max_attempts):
            title, content = collectors.crawl_article_with_newspaper3k(item.url)
            if content and len(content) >= min_len:
                item.title = title or item.title or 'Untitled'
                item.content = content
                item.crawl_status = "CRAWLED"
                db.commit()
                success += 1
                ok = True
                break
        if not ok:
            item.crawl_status = "FAILED"
            db.commit()
    return success


def _gather_articles(db: Session, batch: LetterBatch) -> List[Dict[str, Any]]:
    min_len = settings.LETTER_MIN_CONTENT_LEN
    arts: List[Dict[str, Any]] = []
    for it in db.query(LetterItem).filter(LetterItem.batch_id == batch.id, LetterItem.crawl_status == "CRAWLED"):
        if it.content and len(it.content) >= min_len:
            arts.append({
                'title': it.title or 'Untitled',
                'url': it.url,
                'description': it.description,
                'published_at': None,
                'content': it.content,
            })
    return arts


def prepare_articles(
    db: Session,
    sector: str,
    batch_key: str,
    queries: List[str],
    target_size: int,
    language: str = 'en',
    country: str = 'us',
    fresh: bool = False,
) -> Tuple[LetterBatch, List[Dict[str, Any]]]:
    """High-level orchestration returning batch + usable article dict list."""
    batch = ensure_batch(db, sector, batch_key, fresh=fresh)
    current = db.query(LetterItem).filter(LetterItem.batch_id == batch.id).count()
    if current == 0:
        # 1) 캐시 재활용 먼저
        backfill_from_cache(db, batch, target_size)
        # 2) 부족하면 API 메타 채우기
        have = db.query(LetterItem).filter(LetterItem.batch_id == batch.id).count()
        if have < target_size:
            _api_fill(db, batch, queries, target_size - have, language, country)
    # 3) 크롤링 수행
    _crawl_pending(db, batch)
    arts = _gather_articles(db, batch)
    logger.info(f"prepare_articles 완료: usable={len(arts)}/{target_size}")
    return batch, arts
