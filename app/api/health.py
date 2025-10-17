"""
헬스체크 엔드포인트 모듈

간단한 DB 연결 확인을 수행하여 서비스 및 DB의 연결 상태를
빠르게 확인할 수 있도록 합니다. 프로덕션에서는 추가적인
헬스 체크(종속 서비스, 저장소 검사 등)를 확장할 수 있습니다.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from ..database import get_db


router = APIRouter()


@router.get("/health", tags=["Monitoring"])
def check_health(db: Session = Depends(get_db)):
    """서버 및 데이터베이스 연결 상태를 확인하는 간단한 헬스 체크.

    데이터베이스에 간단한 쿼리(`SELECT 1`)를 수행하고 성공하면
    연결 상태를 'connected'로 응답합니다. 실패 시 'disconnected'를 반환합니다.
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception:
        # 실패 시 내부 예외 메시지는 노출하지 않고 간단한 상태 정보만 반환
        return {"status": "error", "database": "disconnected", "error": "connection_failed"}