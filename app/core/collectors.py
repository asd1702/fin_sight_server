import requests
from newspaper import Article as NewspaperArticle
from newspaper.configuration import Configuration
from pydantic import ValidationError
from ..core.config import settings

from logs.logging_config import get_logger
from app.schemas.external import NaverNewsItemSchema
from .monitoring import monitor_performance

logger = get_logger(__name__)

NAVER_CLIENT_ID = settings.NAVER_CLIENT_ID
NAVER_CLIENT_SECRET = settings.NAVER_CLIENT_SECRET

@monitor_performance(include_memory=True)
def call_naver_api(query: str, display: int = 3) -> list:
    """
    네이버 뉴스 API를 호출하여 기사 메타데이터 리스트를 반환합니다.
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        logger.error("네이버 API 키가 .env 파일에 설정되지 않았습니다")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": "date"}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])
        
        validated_items = []
        for item in items:
            try:
                # NaverNewsItemSchema를 사용하여 데이터 유효성 검사
                validated_item = NaverNewsItemSchema(**item)
                validated_items.append(validated_item.model_dump())
            except ValidationError as e:
                logger.warning(f"네이버 API 응답 데이터 검증 실패. 건너뜁니다. 오류: {e} | 데이터: {item}")
                continue

        logger.info(f"네이버 API '{query}' 키워드로 {len(items)}개 기사 메타데이터 수신 성공.")
        return validated_items
    
    except requests.exceptions.Timeout:
        logger.error(f"네이버 API 호출 중 타임아웃 발생 (query: {query})")
        return []
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"네이버 API HTTP 에러 발생: {http_err} - 응답: {http_err.response.text}")
        return []
    except requests.exceptions.RequestException as e:
        logger.critical(f"네이버 API 호출 중 네트워크 에러 발생: {e}")
        return []
    except ValueError:
        logger.error(f"네이버 API 응답 JSON 파싱 실패 (query: {query})")
        return []

@monitor_performance(include_memory=True)
def crawl_article_with_newspaper3k(url: str) -> tuple[str | None, str | None]:
    """
    User-Agent 설정을 사용하여 기사의 제목과 본문을 추출합니다.
    """
    try:
        # --- User-Agent 설정 ---
        config = Configuration()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
        config.request_timeout = 10

        article = NewspaperArticle(url, language='ko', config=config, fetch_images=False)
        article.download()
        article.parse()
        
        # 제목이나 본문이 비어있는 경우 실패로 간주.
        if not article.title or not article.text:
            logger.debug(f"제목 또는 본문 추출 실패: {url}")
            return None, None

        # 본문 내용이 너무 짧으면 유효하지 않은 기사로 간주.
        if len(article.text) < 200:
            logger.info(f"기사 본문 길이 부족으로 건너뜀: {len(article.text)}자 (최소 200자 필요) - {url}")
            return None, None

        return article.title, article.text
        
    except Exception as e:
        logger.error(f"newspaper3k 파싱 중 에러 발생 (URL: {url}): {e.__class__.__name__} - {e}")
        return None, None
