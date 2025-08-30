from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..database import get_db

router = APIRouter()

@router.get("/health", tags=["Monitoring"])
def check_health(db: Session = Depends(get_db)):
    """
    서버 상태 확인용 헬스 체크 엔드포인트
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": "disconnected", "error": "connection_failed"}