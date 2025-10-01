import yaml
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_CANDIDATE_PATHS = [
    # 1) 기존(잘못 가정) 루트 위치
    Path(__file__).resolve().parent.parent.parent / "prompts.yaml",
    # 2) 실제 현재 구조(app/prompts/prompts.yaml)
    Path(__file__).resolve().parent.parent / "prompts" / "prompts.yaml",
    # 3) 혹시 있을 수 있는 별도 prompts 디렉터리
    Path(__file__).resolve().parent.parent.parent / "prompts" / "prompts.yaml",
]

def _resolve_prompts_file() -> Path | None:
    for p in _CANDIDATE_PATHS:
        if p.is_file():
            return p
    return None

PROMPTS_FILE = _resolve_prompts_file()
if not PROMPTS_FILE:
    logger.error("심각한 오류: 어떤 경로에서도 prompts.yaml을 찾지 못했습니다. 후보: %s", _CANDIDATE_PATHS)

def load_all_prompts() -> dict:
    """YAML 파일에서 모든 프롬프트를 불러와 딕셔너리로 반환.
    다중 위치 탐색 & 예외 안전.
    """
    if not PROMPTS_FILE:
        return {}
    try:
        with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                logger.error("prompts.yaml 최상위 구조가 dict가 아닙니다.")
                return {}
            return data
    except FileNotFoundError:
        logger.error(f"심각한 오류: 프롬프트 파일({PROMPTS_FILE})을 찾을 수 없습니다.")
        return {}
    except Exception as e:
        logger.error(f"프롬프트 파일({PROMPTS_FILE}) 로드 중 오류 발생: {e}")
        return {}

ALL_PROMPTS = load_all_prompts()

def reload_prompts() -> None:
    global ALL_PROMPTS
    ALL_PROMPTS = load_all_prompts()
    logger.info("프롬프트 재로딩 완료: keys=%s", list(ALL_PROMPTS.keys()))

def get_prompt(topic: str, prompt_type: str, fallback_topic: str | None = None) -> str | None:
    """메모리에 로드된 프롬프트 데이터에서 주제/타입에 맞는 프롬프트 반환.

    fallback_topic: topic 키 없을 때 대체 키 한 번 더 탐색 (예: company 기본 프롬프트 재사용)
    """
    prompt = (ALL_PROMPTS.get(topic) or {}).get(prompt_type)
    if not prompt and fallback_topic:
        prompt = (ALL_PROMPTS.get(fallback_topic) or {}).get(prompt_type)
        if prompt:
            logger.warning("'%s' 프롬프트 없어서 fallback '%s' 사용 (%s)", topic, fallback_topic, prompt_type)
    if not prompt:
        logger.error("'%s'에 대한 '%s' 프롬프트를 찾을 수 없습니다.", topic, prompt_type)
        return None
    return prompt