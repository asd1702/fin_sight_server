import yaml
from pathlib import Path
import json
from ..config import settings
from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError
from sqlalchemy.orm import Session

from ...models.statistic_model.statistic import Indicator
from logs.logging_config import get_logger
from ..monitoring import monitor_performance

from ...utils.prompt_manager import get_prompt

logger = get_logger(__name__)

# OpenAI 클라이언트 초기화
OPENAI_API_KEY = settings.OPENAI_API_KEY
if not OPENAI_API_KEY:
    raise ValueError("'.env' 파일에 OPENAI_API_KEY가 설정되지 않았습니다.")

# 타임아웃/재시도는 설정에서 가져오되 기본값 제공
_LLM_TIMEOUT = getattr(settings, 'LETTER_LLM_TIMEOUT_SECS', 60.0)
_LLM_RETRIES = getattr(settings, 'LETTER_LLM_CLIENT_RETRIES', 3)
openai_client = OpenAI(api_key=OPENAI_API_KEY, max_retries=_LLM_RETRIES, timeout=_LLM_TIMEOUT)




@monitor_performance(include_memory=True)
def analyze_article_with_llm(db: Session, content: str, topic: str, model="gpt-4o-mini") -> dict | None:
    """
    기사 원문을 LLM에 보내 배경지식, 키워드, 관련 통계 지표 ID 등을 분석하고 추출합니다.

    Args:
        db (Session): 데이터베이스 세션.
        content (str): 분석할 기사 원문 전체.
        model (str, optional): 사용할 OpenAI 모델. Defaults to "gpt-4o-mini".

    Returns:
        dict | None: 분석 결과가 담긴 딕셔너리 또는 실패 시 None.
    """
    system_prompt = get_prompt(topic, "analyze")

    if not system_prompt:
        return None

    # 완성된 프롬프트로 LLM API를 호출합니다.
    result_str = ""  # 에러 로깅을 위해 변수를 미리 선언
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        result_str = response.choices[0].message.content
        result = json.loads(result_str)
        logger.info("LLM 분석 데이터 수신 및 파싱 성공 (topic: {topic})")
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"LLM 응답이 유효한 JSON 형식이 아닙니다: {e}\nRaw response: {result_str}")
        return None
    except (APIConnectionError, APIStatusError) as e:
        logger.error(f"OpenAI 챗 API 연결 에러 발생: {e.__class__.__name__} - {e}")
        return None
    except Exception as e:
        logger.critical(f"OpenAI 챗 API 호출 중 예상치 못한 에러 발생: {e}", exc_info=True)
        return None


@monitor_performance(include_memory=True)
def build_column_outline_with_llm(db: Session, company: str, articles: list[dict], topic: str | None = None, model: str = "gpt-4o-mini") -> dict | None:
    """
    기사 5~10개를 번들로 LLM에 전달해 에디터 친화적인 칼럼 초안(JSON)을 생성.
    기사 메타는 citations에 반영하고, 본문은 섹션으로 재구성.
    """
    # topic이 명시되지 않으면 company를 topic 키로 시도하고, 없으면 'company' 프롬프트로 fallback
    _topic_key = topic or company
    system_prompt = get_prompt(_topic_key, "bundle", fallback_topic="company")

    if not system_prompt:
        return None

    # 설정값
    MAX_ARTICLES = min(len(articles), getattr(settings, "LETTER_LLM_MAX_ARTICLES", 8))
    BASE_BUDGET = getattr(settings, "LETTER_LLM_INPUT_BUDGET", 22000)
    MAX_TOKENS = getattr(settings, "LETTER_LLM_MAX_TOKENS", 1500)

    def _compact(arts: list[dict], max_articles: int, budget: int) -> list[dict]:
        per_article = max(1200, min(6000, budget // max(max_articles, 1)))
        compact: list[dict] = []
        for it in arts[:max_articles]:
            content = (it.get("content") or "")
            head = content[: per_article // 2]
            tail = content[-(per_article - len(head)):] if len(content) > per_article else ""
            compact.append({
                "title": it.get("title"),
                "url": it.get("url"),
                "description": it.get("description"),
                "published_at": it.get("published_at"),
                "content": head + ("\n...\n" if tail else "") + tail,
            })
        return compact

    # 적응형 시도: (기사 수, 예산)을 점진적으로 줄이며 최대 3회 시도
    attempts = [
        (MAX_ARTICLES, BASE_BUDGET),
        (min(MAX_ARTICLES, 6), int(BASE_BUDGET * 0.7)),
        (min(MAX_ARTICLES, 4), int(BASE_BUDGET * 0.5)),
    ]

    last_error: Exception | None = None
    for idx, (ma, budget) in enumerate(attempts, start=1):
        compact_items = _compact(articles, ma, budget)
        user_payload = {"company": company, "articles": compact_items}
        try:
            response = openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=MAX_TOKENS,
            )
            content = response.choices[0].message.content
            data = json.loads(content)

            # 최소 필드 검증/보정
            data.setdefault("company", company)
            data.setdefault("sections", [])
            for sec in data.get("sections", []):
                # body를 문자열로 강제(간혹 리스트로 나오는 경우 방지)
                body = sec.get("body")
                if isinstance(body, list):
                    sec["body"] = " ".join(str(x) for x in body if x)
                elif body is None:
                    sec["body"] = ""
                # bullets는 리스트 보장
                if not isinstance(sec.get("bullets"), list):
                    sec["bullets"] = []
                if "needs_visual" not in sec:
                    body = (sec.get("body") or "") + " " + " ".join(sec.get("bullets") or [])
                    keywords = [
                        "시가총액", "실적", "매출", "성장률", "점유율", "분기", "달러", "%",
                        "earnings", "IR", "call", "guidance", "가이던스",
                        "컨퍼런스", "conference", "행사", "일정", "발표 예정", "발표 일정"
                    ]
                    sec["needs_visual"] = any(k in body for k in keywords)
                sec.setdefault("visual_hint", None)

            if "citations" not in data:
                data["citations"] = [{"title": it["title"], "url": it["url"]} for it in compact_items if it.get("url")]

            logger.info(f"LLM 칼럼 초안(JSON) 생성 성공 - 시도 {idx}/{len(attempts)} (topic: {topic}, 기사 {ma}개, 예산 {budget})")
            return data
        except json.JSONDecodeError as e:
            last_error = e
            logger.error(f"LLM 번들 응답 JSON 파싱 실패(시도 {idx}): {e}")
            continue
        except (APIConnectionError, APIStatusError) as e:
            last_error = e
            logger.error(f"OpenAI 챗 API 연결 에러(시도 {idx}): {e.__class__.__name__} - {e}")
            continue
        except Exception as e:
            last_error = e
            logger.critical(f"번들 칼럼 생성 중 예기치 못한 오류(시도 {idx}): {e}", exc_info=True)
            continue

    if last_error:
        logger.error(f"LLM 칼럼 생성 실패(모든 시도 소진): {last_error}")
    return None
