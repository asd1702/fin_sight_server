import os
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = os.getenv("ENV_FILE", ".env.dev")

class Settings(BaseSettings):
    """
    .env 파일의 모든 설정 변수를 관리하는 클래스
    """
    
    # --- 외부 API 키 ---
    OPENAI_API_KEY: str
    NAVER_CLIENT_ID: str
    NAVER_CLIENT_SECRET: str
    ECOS_API_KEY: str

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

    # --- Pydantic 설정 ---
    model_config = SettingsConfigDict(
        env_file=ENV_FILE, 
        env_file_encoding='utf-8'
    )

settings = Settings()

print(f"Settings loaded successfully from: {ENV_FILE}")