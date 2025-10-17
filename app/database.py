"""
데이터베이스 연결 설정 모듈

이 모듈은 애플리케이션 전체에서 사용하는 SQLAlchemy 엔진과 세션 팩토리를
정의합니다. 환경 변수 또는 설정 객체에서 `DATABASE_URL`을 가져와 엔진을 생성합니다.

주의: 이 파일은 DB 연결을 설정하는 역할만 하며, 세션 관리는
`get_db` FastAPI 의존성(generator)를 통해 요청 단위로 이루어집니다.
"""

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


# 설정에서 DATABASE_URL 가져오기
DATABASE_URL = settings.DATABASE_URL

if DATABASE_URL is None:
    # 애플리케이션이 시작되기 전에 필수 환경변수가 설정되어 있어야 함
    raise ValueError("DATABASE_URL environment variable is not set.")


# SQLAlchemy 엔진 생성
# - 필요에 따라 create_engine에 추가 옵션(echo, pool_size 등)을 설정 가능
engine = create_engine(DATABASE_URL)


# 세션 팩토리(SessionLocal) 생성
# - autocommit, autoflush 동작을 명시적으로 비활성화하여
#   요청 단위로 명시적 커밋/플러시를 하도록 함
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI 의존성: 요청 단위 DB 세션을 제공하는 generator.

    사용법 예:
        def endpoint(db: Session = Depends(get_db)):
            # db는 SQLAlchemy 세션

    generator 형태로 정의되어 있으며, 호출 후 반드시 `db.close()`를 통해
    세션을 정리합니다. 로직 변경 없이 주석만 추가했습니다.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()