"""
애플리케이션 설정 관리 모듈

환경 파일 선택 우선순위를 처리하고 Pydantic 기반의 `Settings` 클래스를
정의합니다. 애플리케이션 전역에서 `settings` 인스턴스를 통해 설정 값을 사용합니다.

ENV 파일 우선순위:
  1. 환경변수 `ENV_FILE`에 지정된 파일
  2. 현재 작업 디렉터리의 `.env`
  3. `.env.dev`
  4. `.env.prod`
  기본값은 `.env.dev`입니다.

설정값은 Pydantic의 `BaseSettings`를 확장하여 타입 검증과 기본값을 제공합니다.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict


# ENV 파일 선택 우선순위: ENV_FILE 환경변수 > .env > .env.dev > .env.prod
_env_file_from_env = os.getenv("ENV_FILE")
if _env_file_from_env:
    ENV_FILE = _env_file_from_env
elif os.path.exists(".env"):
    ENV_FILE = ".env"
elif os.path.exists(".env.dev"):
    ENV_FILE = ".env.dev"
elif os.path.exists(".env.prod"):
    ENV_FILE = ".env.prod"
else:
    # 개발 편의를 위해 기본값은 .env.dev
    ENV_FILE = ".env.dev"


class Settings(BaseSettings):
    """애플리케이션에서 사용하는 모든 설정 항목을 정의합니다.

    각 필드는 `.env` 또는 지정된 ENV 파일에서 읽어오며, 타입 검증과
    기본값(있는 경우)을 제공합니다. 주석은 개발자가 필드 목적을
    빠르게 이해하도록 도움을 줍니다.
    """
    # --- 외부 API 키 ---
    OPENAI_API_KEY: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    ECOS_API_KEY: str
    NEWS_DATA_API_KEY: str

    # --- 데이터베이스 연결 설정 ---
    DATABASE_URL: str
    
    # --- 외부 서비스 URL ---
    # Redis 등 캐시 저장소를 사용하는 경우 URL을 지정
    REDIS_URL: str | None = None

    # --- API 서버 설정 ---
    DEBUG: bool
    LOG_LEVEL: str

    # --- 파이프라인 설정 ---
    BATCH_SIZE: int
    MAX_WORKERS: int
    RETRY_ATTEMPTS: int

    # --- 임베딩 모델 설정 ---
    EMBEDDING_MODEL: str | None = None
    EMBEDDING_DIMENSION: int | None = None

    # --- LLM 설정 ---
    LLM_MODEL: str
    MAX_TOKENS: int
    TEMPERATURE: float  # 0도 실수로 처리 가능하여 float으로 지정

    # --- 뉴스레터 파이프라인 설정(기본값 제공) ---
    # 임시 데이터 TTL(시간)
    LETTER_TTL_HOURS: int = 24
    # 크롤링 재시도 횟수
    LETTER_MAX_CRAWL_ATTEMPTS: int = 2
    # LLM 재시도 횟수
    LETTER_MAX_LLM_ATTEMPTS: int = 2
    # 본문 최소 길이(유효성 판단)
    LETTER_MIN_CONTENT_LEN: int = 200
    # LLM 호출 최소 기사 수
    LETTER_MIN_ARTICLES: int = 3
    # LLM 모델명(파이프라인 전용)
    LETTER_LLM_MODEL: str = "gpt-4o-mini"
    # 캐시 재활용 신선도(일)
    LETTER_CACHE_MAX_AGE_DAYS: int = 14

    # --- Pydantic 설정 ---
    # model_config를 사용해 env_file 경로와 인코딩, 추가 필드 처리 방법을 지정
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra='ignore'
    )


settings = Settings()

print(f"Settings loaded successfully from: {ENV_FILE}")