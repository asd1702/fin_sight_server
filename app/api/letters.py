"""
뉴스레터(레터) 관련 API 엔드포인트

이 모듈은 레터 초안 조회, 배치 목록 조회, 그리고 배치 퍼블리시(발행)를
제공합니다. Pydantic 스키마는 DB 모델의 속성을 기반으로 직렬화에 사용됩니다.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models.news_letter import LetterBatch, LetterOutline
from pydantic import BaseModel


router = APIRouter(prefix="/api/letters", tags=["letters"])


class LetterOutlineSchema(BaseModel):
    """단일 레터 배치의 초안(Outline) 응답 스키마

    `from_attributes = True`로 설정하여 ORM 객체의 속성에서 자동으로
    값을 읽어올 수 있도록 합니다.
    """
    batch_id: int
    sector: str
    key_word: str
    status: str
    outline_version: int
    prompt_key: Optional[str] = None
    published_at: Optional[str] = None
    outline: dict

    class Config:
        from_attributes = True


class LetterListItem(BaseModel):
    """배치 목록 응답에 사용되는 경량 스키마"""
    batch_id: int
    sector: str
    key_word: str
    created_at: str
    status: str
    outline_version: int

    class Config:
        from_attributes = True


class BulkPublishResponse(BaseModel):
    published: int
    updated_batch_ids: List[int]
    skipped_already_delivered: int


@router.get("/{sector}/{key}", response_model=LetterOutlineSchema)
def get_latest_letter(sector: str, key: str, db: Session = Depends(get_db)):
    """주어진 (sector, key)에 대해 최신 배치의 초안을 반환합니다."""
    batch = (
        db.query(LetterBatch)
        .filter(LetterBatch.sector == sector, LetterBatch.key_word == key)
        .order_by(LetterBatch.created_at.desc())
        .first()
    )
    if not batch or not batch.outline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 (sector,key) 초안이 없습니다")
    o = batch.outline
    return LetterOutlineSchema(
        batch_id=batch.id,
        sector=batch.sector,
        key_word=batch.key_word,
        status=o.status,
        outline_version=o.outline_version,
        prompt_key=o.prompt_key,
        published_at=(o.published_at.isoformat() if o.published_at else None),
        outline=o.outline,
    )


@router.get("/{sector}/{key}/history", response_model=List[LetterListItem])
def list_letter_batches(sector: str, key: str, limit: int = 20, db: Session = Depends(get_db)):
    """주어진 (sector, key)에 대한 배치 이력을 반환합니다."""
    q = (
        db.query(LetterBatch)
        .filter(LetterBatch.sector == sector, LetterBatch.key_word == key)
        .order_by(LetterBatch.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    items: List[LetterListItem] = []
    for b in q:
        if b.outline:
            items.append(
                LetterListItem(
                    batch_id=b.id,
                    sector=b.sector,
                    key_word=b.key_word,
                    created_at=b.created_at.isoformat() if b.created_at else "",
                    status=b.outline.status,
                    outline_version=b.outline.outline_version,
                )
            )
    return items


@router.post("/{sector}/{key}/{batch_id}/publish", response_model=LetterOutlineSchema)
def publish_letter(sector: str, key: str, batch_id: int, db: Session = Depends(get_db)):
    """특정 배치의 초안을 'delivered' 상태로 변경하여 발행 처리합니다.

    이미 발행된 경우 기존 상태를 그대로 반환합니다.
    """
    batch = (
        db.query(LetterBatch)
        .filter(LetterBatch.id == batch_id, LetterBatch.sector == sector, LetterBatch.key_word == key)
        .first()
    )
    if not batch or not batch.outline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대상 초안이 없습니다")
    o = batch.outline
    if o.status == 'delivered':
        # 이미 발행된 경우, 현재 상태를 그대로 반환
        return LetterOutlineSchema(
            batch_id=batch.id,
            sector=batch.sector,
            key_word=batch.key_word,
            status=o.status,
            outline_version=o.outline_version,
            prompt_key=o.prompt_key,
            published_at=(o.published_at.isoformat() if o.published_at else None),
            outline=o.outline,
        )
    from datetime import datetime, timezone
    o.status = 'delivered'
    o.published_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(o)
    return LetterOutlineSchema(
        batch_id=batch.id,
        sector=batch.sector,
        key_word=batch.key_word,
        status=o.status,
        outline_version=o.outline_version,
        prompt_key=o.prompt_key,
        published_at=(o.published_at.isoformat() if o.published_at else None),
        outline=o.outline,
    )