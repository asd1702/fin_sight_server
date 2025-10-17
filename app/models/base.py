"""
SQLAlchemy declarative base 정의

프로젝트 전반에서 ORM 모델이 이 `Base`를 상속하여 선언됩니다.
"""

from sqlalchemy.orm import declarative_base

# 모든 ORM 모델의 공통 베이스 클래스
Base = declarative_base()
