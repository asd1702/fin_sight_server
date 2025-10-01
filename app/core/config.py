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
    ENV_FILE = ".env.dev"

class Settings(BaseSettings):
    """
    .env 파일의 모든 설정 변수를 관리하는 클래스
    """
    
    # --- 외부 API 키 ---
    OPENAI_API_KEY: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    ECOS_API_KEY: str
    NEWS_DATA_API_KEY: str

    # --- 데이터베이스 연결 설정 ---
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str
    DATABASE_URL: str
    
    # --- 외부 서비스 URL ---
    REDIS_URL: str

    # --- API 서버 설정 ---
    DEBUG: bool
    LOG_LEVEL: str

    # --- 파이프라인 설정 ---
    BATCH_SIZE: int
    MAX_WORKERS: int
    RETRY_ATTEMPTS: int

    # --- 임베딩 모델 설정 ---
    EMBEDDING_MODEL: str
    EMBEDDING_DIMENSION: int

    # --- LLM 설정 ---
    LLM_MODEL: str
    MAX_TOKENS: int
    TEMPERATURE: float # 0도 실수로 처리 가능하여 float으로 지정

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
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, 
        env_file_encoding='utf-8'
    )

settings = Settings()

print(f"Settings loaded successfully from: {ENV_FILE}")