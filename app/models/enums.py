"""
열거형(enum) 정의 모듈

도메인에서 사용하는 간단한 상태 열거형들을 정의합니다. 문자열 기반 Enum을 사용하여
직렬화/역직렬화시 편리하게 활용할 수 있습니다.
"""

import enum


class ArticleStatus(str, enum.Enum):
    """기사 상태를 나타내는 열거형.

    PENDING: 신규 수집 또는 아직 처리되지 않은 상태
    PROCESSING: 처리 중
    PROCESSED: LLM 분석 등 처리가 완료된 상태
    FAILED: 처리 실패
    """
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
