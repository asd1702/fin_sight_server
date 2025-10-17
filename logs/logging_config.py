import logging
import os
from typing import List


"""
로깅 설정 모듈

이 모듈은 환경 변수로부터 로깅 설정을 읽어와서 전역 로거를 설정합니다.

환경 변수 요약:
  - LOG_DIR: 파일 로깅을 사용할 때 로그 파일을 저장할 디렉터리 (기본: 'logs')
  - LOG_LEVEL: 전역 로그 레벨 (예: 'INFO', 'DEBUG')
  - LOG_TO_FILE: 파일 로깅 활성화 여부 (기본: 활성화). '0', 'false', 'no' 중 하나면 비활성화
"""


# 로그 디렉터리 및 설정 가져오기
LOG_DIR = os.getenv("LOG_DIR", "logs")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
# 파일 로깅을 끄려면 LOG_TO_FILE을 '0' 또는 'false'로 설정
ENABLE_FILE_LOG = os.getenv("LOG_TO_FILE", "1").lower() not in ("0", "false", "no")


# logging 모듈 상수로 변환 (기본값: INFO)
log_level = getattr(logging, LOG_LEVEL, logging.INFO)


# 기본 핸들러: stdout
handlers: List[logging.Handler] = [logging.StreamHandler()]


if ENABLE_FILE_LOG:
    try:
        # 로그 디렉터리 생성(권한 문제 발생 가능)
        if not os.path.exists(LOG_DIR):
            os.makedirs(LOG_DIR, exist_ok=True)
        file_path = os.path.join(LOG_DIR, "pipeline.log")
        # FileHandler를 앞쪽에 넣어 파일 로그가 우선 기록되도록 함
        handlers.insert(0, logging.FileHandler(file_path, encoding="utf-8"))
    except Exception as e:  # PermissionError or others
        # 디렉터리 생성/파일 핸들러 실패 시 stdout만 사용하도록 폴백
        print(f"[logging] WARNING: file logging disabled ({e}). Using stdout only.")


logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=handlers,
)


def get_logger(name: str) -> logging.Logger:
    """
    이름에 해당하는 로거를 반환합니다.

    사용 예:
      logger = get_logger(__name__)
      logger.info("메시지")

    반환값:
      logging.Logger 인스턴스
    """
    return logging.getLogger(name)