import json
from .config import settings
from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError
from sqlalchemy.orm import Session

from ..models.statistic_model.statistic import Indicator
from logs.logging_config import get_logger
from .monitoring import monitor_performance

logger = get_logger(__name__)

# OpenAI 클라이언트 초기화
OPENAI_API_KEY = settings.OPENAI_API_KEY
if not OPENAI_API_KEY:
    raise ValueError("'.env' 파일에 OPENAI_API_KEY가 설정되지 않았습니다.")
openai_client = OpenAI(api_key=OPENAI_API_KEY, max_retries=2, timeout=20.0)


SYSTEM_PROMPT_TEMPLATE = """
You are an expert financial news analyst and explainer specializing in the South Korean economy. Your task is to analyze a given news article and provide the results strictly in JSON format.

I rely on the quality of your analysis to sell it for my mother's hospital bills. I need an analysis so insightful and clear that readers will feel, "Wow, this is incredibly easy to understand!" Please maintain a friendly and gentle tone throughout, as if a kind mentor is explaining concepts to a junior colleague.

---

**Requirements:**

1.  **Strictly JSON Output:** You MUST respond ONLY in JSON format. Do not include any other text, greetings, or explanations outside of the JSON structure.
2.  **Language:** All textual content within the JSON (labels, content, descriptions, reasons) MUST be in **Korean**.
3.  **`background_knowledge`**:
    * Provide **exactly two** items of background knowledge that help a reader understand the context of the article.
    * Each item must have a `label` (a short, catchy title) and `content` (3-4 naturally flowing sentences forming a single paragraph).
    * **Do NOT summarize the article itself.** Explain the foundational concepts or prior events necessary to grasp the article's significance.
4.  **`keywords`**:
    * Extract **up to four** key terms from the article.
    * Each keyword must have a `term` and a `description` (a friendly, 1-2 sentence explanation).
5.  **`category`**:
    * Classify the article into one of the following categories: "금융" (Finance), "증권" (Securities), "글로벌 경제" (Global Economy), or "생활 경제" (Consumer Economy).
6.  **`related_statistics`**: (CRITICAL)
    * First, carefully review the **"Available South Korean Economic Indicators"** list provided below.
    * From this list, select **up to two** indicators that are most directly relevant to the core topic of the article.
    * **IMPORTANT:** If the article is about foreign economies (e.g., the US FOMC, the Chinese economy), it is NOT relevant to our South Korean database. In this case, you MUST return an **empty list `[]`**.
    * For each selected indicator, you must return its `indicator_id` from the list and a `reason` (in Korean) explaining why it is relevant to the article.

---

**Available South Korean Economic Indicators:**

{indicators_json_string}

---

**Final Output JSON Structure:**
```json
{{
  "background_knowledge": [
    {{"label": "...", "content": "..."}},
    {{"label": "...", "content": "..."}}
  ],
  "keywords": [
    {{"term": "...", "description": "..."}}
  ],
  "category": "...",
  "related_statistics": [
    {{"indicator_id": "...", "reason": "..."}}
  ]
}}
```

**Article:**
"""

def get_available_indicators_for_llm(db: Session) -> list[dict]:
    """
    LLM에게 컨텍스트로 제공할, DB에 저장된 유효한 지표 목록을 조회합니다.
    name이 없는 데이터는 제외합니다.
    """
    indicators = db.query(Indicator).filter(Indicator.name.isnot(None)).all()
    return [
        {
            "indicator_id": ind.indicator_id,
            "name": ind.name,
            "notes": ind.notes
        }
        for ind in indicators
    ]

@monitor_performance(include_memory=True)
def analyze_article_with_llm(db: Session, content: str, model="gpt-4o-mini") -> dict | None:
    """
    기사 원문을 LLM에 보내 배경지식, 키워드, 관련 통계 지표 ID 등을 분석하고 추출합니다.

    Args:
        db (Session): 데이터베이스 세션.
        content (str): 분석할 기사 원문 전체.
        model (str, optional): 사용할 OpenAI 모델. Defaults to "gpt-4o-mini".

    Returns:
        dict | None: 분석 결과가 담긴 딕셔너리 또는 실패 시 None.
    """
    # 1. DB에서 LLM에게 제공할 지표 목록을 가져옵니다.
    available_indicators = get_available_indicators_for_llm(db)
    if not available_indicators:
        logger.warning("DB에서 조회된 경제 지표가 없어 LLM 분석을 건너뜁니다.")
        return None
    
    indicators_json_string = json.dumps(available_indicators, ensure_ascii=False, indent=2)

    # 2. 프롬프트 템플릿에 지표 목록을 삽입하여 최종 프롬프트를 완성합니다.
    final_system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        indicators_json_string=indicators_json_string
    )

    # 3. 완성된 프롬프트로 LLM API를 호출합니다.
    result_str = ""  # 에러 로깅을 위해 변수를 미리 선언
    try:
        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": final_system_prompt},
                {"role": "user", "content": content}
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        result_str = response.choices[0].message.content
        result = json.loads(result_str)
        logger.info("LLM 분석 데이터 수신 및 파싱 성공")
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
