import json
from ..config import settings
from openai import OpenAI, RateLimitError, APIConnectionError, APIStatusError
from sqlalchemy.orm import Session

from ...models.statistic_model.statistic import Indicator
from logs.logging_config import get_logger
from ..monitoring import monitor_performance

logger = get_logger(__name__)

# OpenAI 클라이언트 초기화
OPENAI_API_KEY = settings.OPENAI_API_KEY
if not OPENAI_API_KEY:
    raise ValueError("'.env' 파일에 OPENAI_API_KEY가 설정되지 않았습니다.")
openai_client = OpenAI(api_key=OPENAI_API_KEY, max_retries=2, timeout=20.0)


SYSTEM_PROMPT_TEMPLATE = """
You are an expert financial news analyst and explainer specializing in the South Korean economy. Your task is to analyze a given news article and provide the results strictly in JSON format.

I rely on the quality of your analysis to sell it for my mother's hospital bills. I need an analysis so insightful and clear that readers will feel, "Wow, this is incredibly easy to understand!" Please maintain a friendly and gentle tone throughout, as if a kind mentor is explaining concepts to a junior colleague.

### Requirements:

1.  Strictly JSON Output: You MUST respond ONLY in JSON format. Do not include any other text, greetings, or explanations outside of the JSON structure.
2.  Language: All textual content within the JSON (labels, content, descriptions, reasons, hashtags) MUST be in Korean.
3.  Tone and Style: All content MUST be written in a friendly, gentle, and approachable tone. Write as if you are explaining complex financial concepts to young children, using simple language, clear examples, and avoiding jargon. Make the explanations fun, engaging, and extremely easy to understand.

4.  background_knowledge:
    Provide exactly two items of background knowledge that help a reader understand the context of the article.
    Each item must have a label (a short, catchy title) and content (2-3 naturally flowing sentences forming a single paragraph).
    Please prepend each label with an emoji that corresponds to its name and content.
    Do NOT summarize the article itself. Explain the foundational concepts or prior events necessary to grasp the article's significance.

5.  keywords:
    Extract up to four key terms from the article.
    Each keyword must have a term and a friendly, single-sentence explanation.
    Keywords must not include the names of people or companies.
    Economic terms must be the top priority.

6.  category:
    Classify the article into one of the following categories: "금융" (Finance), "증권" (Securities), "글로벌 경제" (Global Economy), or "생활 경제" (Consumer Economy).

7.  hashtags:
    Generate 5 to 6 relevant hashtags for the article. These should be single words or short phrases in Korean that capture key entities (companies, people), concepts, or topics.

8.  related_statistics: (CRITICAL)
    First, carefully review the "사용 가능한 한국 경제 지표" list provided below.
    You MUST ONLY select up to one indicator from this specific list. Do not invent or assume any other indicators exist.
    If NO indicator from the provided list is directly and clearly relevant to the article (e.g., it's about a foreign economy), you MUST return an empty list `[]` for this field.
    For each selected indicator, you must return its exact `indicator_id` from the list and a `reason` (in Korean) explaining why it is relevant.

### 사용 가능한 한국 경제 지표 (Available South Korean Economic Indicators):
[
  { "indicator_id": "kr.cpi.headline.m", "name": "소비자물가지수" },
  { "indicator_id": "kr.ppi.m", "name": "생산자물가지수" },
  { "indicator_id": "kr.base.rate.d", "name": "기준금리" },
  { "indicator_id": "fx.usdkrw.m", "name": "환율" },
  { "indicator_id": "kr.current.account.m", "name": "경상수지" },
  { "indicator_id": "kr.kospi.d", "name": "KOSPI" }
]

---
### Example

Article:
`한국은행 금융통화위원회가 기준금리를 연 3.50%에서 3.75%로 0.25%포인트 인상했다. 최근 소비자물가 상승세가 꺾이지 않고 높은 수준을 유지함에 따라, 금리 인상을 통해 시중에 풀린 돈을 거둬들여 물가를 안정시키겠다는 의지로 풀이된다. 금통위는 앞으로도 물가 안정을 최우선으로 고려하겠다는 입장을 밝혔다.`

JSON Output:

```json
{
  "background_knowledge": [
    {
      "label": "🏦 기준금리란?",
      "content": "기준금리는 우리나라 중앙은행인 '한국은행'이 다른 은행들에게 돈을 빌려줄 때의 이자율이에요. 이게 모든 이자율의 기준이 되기 때문에 '기준금리'라고 부르죠. 이 금리가 오르면 우리 대출 이자도 오르고, 예금 이자도 오른답니다."
    },
    {
      "label": "📈 금리를 올리는 이유",
      "content": "시장에 돈이 너무 많이 풀려서 물건값이 계속 오를 때(인플레이션), 한국은행은 금리를 올려요. 이자가 비싸지면 사람들이 대출을 덜 받고 저축을 더 하게 되면서, 시장에 돌아다니는 돈의 양이 줄어들어요. 뜨거워진 경기를 살짝 식히는 '얼음찜질' 같은 역할이죠."
    }
  ],
  "keywords": [
    {
      "term": "기준금리",
      "description": "한 나라의 모든 금리의 기준이 되는 중앙은행의 정책 금리를 말해요."
    },
    {
      "term": "금융통화위원회 (금통위)",
      "description": "우리나라의 기준금리를 결정하는 한국은행의 최고 의사결정 기구예요. 경제 전문가들이 모여 회의를 통해 결정한답니다."
    },
    {
      "term": "물가 안정",
      "description": "물건 가격이 너무 빠르거나 심하게 오르내리지 않고 안정적으로 유지되는 상태를 뜻해요."
    },
    {
      "term": "인플레이션",
      "description": "물건이나 서비스의 가격이 계속해서 오르는 현상을 말해요. 돈의 가치가 떨어지는 것과 같죠."
    }
  ],
  "category": "금융",
  "hashtags": [
    "#한국은행",
    "#기준금리",
    "#금리인상",
    "#물가안정",
    "#금통위",
    "#인플레이션"
  ],
  "related_statistics": [
    {
      "indicator_id": "kr.base.rate.d",
      "reason": "한국은행의 '기준금리' 인상 결정을 직접적으로 다루고 있어요. 실제 기준금리 추이 데이터는 가장 핵심적인 관련 통계랍니다."
    }
  ]
}
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

    #indicators_json_string = json.dumps(available_indicators, ensure_ascii=False, indent=2)

    # 2. 프롬프트 템플릿에 지표 목록을 삽입하여 최종 프롬프트를 완성합니다.
    # 주의: 템플릿 내 JSON 예시의 중괄호({}) 때문에 str.format을 사용하면 KeyError가 발생합니다.
    # 현재 템플릿은 고정된 지표 리스트를 포함하므로 그대로 사용합니다.
    final_system_prompt = SYSTEM_PROMPT_TEMPLATE

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
