from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models.news_letter import LetterBatch, LetterOutline
from pydantic import BaseModel

router = APIRouter(prefix="/api/letters", tags=["letters"])

class LetterOutlineSchema(BaseModel):
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
    batch = (
        db.query(LetterBatch)
        .filter(LetterBatch.id == batch_id, LetterBatch.sector == sector, LetterBatch.key_word == key)
        .first()
    )
    if not batch or not batch.outline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="대상 초안이 없습니다")
    o = batch.outline
    if o.status == 'delivered':
        # already published
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