import requests
from newspaper import Article as NewspaperArticle
from newspaper.configuration import Configuration
from pydantic import ValidationError
from ..config import settings

from logs.logging_config import get_logger
from app.schemas.external import NewsDataItemSchema
from ..monitoring import monitor_performance

logger = get_logger(__name__)

NEWS_DATA_API_KEY = settings.NEWS_DATA_API_KEY

@monitor_performance(include_memory=True)
def call_news_data_api(query: list[str] = None, size: int = 10, language: str = "en", country: str = "us", categories: list[str] = None) -> list:
    """NewsData API 호출.

    변경 사항:
      - 기존 'query' 파라미터 → 'q' 로 교체 (422 UnsupportedParameter 대응)
      - 다중 query 리스트는 OR 로 결합: q="term1 OR term2 OR term3"
      - 422 발생 시 단일 키워드 순차 fallback 재시도
    """
    if not NEWS_DATA_API_KEY:
        logger.error("NEWS_DATA_API_KEY가 .env 파일에 설정되지 않았습니다")
        return []

    base_url = "https://newsdata.io/api/1/news"

    # q 구성
    q_value = None
    if query:
        # 공백 트리밍 및 중복 제거
        cleaned = [q.strip() for q in query if q and q.strip()]
        # 너무 긴 OR 체인은 API 거부 가능 → 길이 제한(임시 7개) 후 나머지 무시
        if len(cleaned) > 7:
            logger.debug(f"쿼리 개수 {len(cleaned)}개 → 7개로 축약")
            cleaned = cleaned[:7]
        if cleaned:
            q_value = " OR ".join(cleaned)

    params = {
        "apikey": NEWS_DATA_API_KEY,
        "country": country,
        "language": language,
        "size": size,
    }
    if q_value:
        params["q"] = q_value
    if categories:
        params["category"] = ",".join(categories)

    def _do_request(p):
        try:
            resp = requests.get(base_url, params=p, timeout=10)
            # 422는 별도 처리 위해 raise 전 상태코드 확인
            if resp.status_code == 422:
                return resp, '422'
            resp.raise_for_status()
            return resp, None
        except requests.exceptions.Timeout:
            logger.error(f"NEWS_DATA_API 타임아웃 (params={ {k:v for k,v in p.items() if k!='apikey'} })")
            return None, 'timeout'
        except requests.exceptions.RequestException as e:
            logger.error(f"NEWS_DATA_API 네트워크 오류: {e}")
            return None, 'network'

    resp, err = _do_request(params)
    # 422 fallback 로직: 개별 키워드로 순차 재시도
    if err == '422' and query:
        logger.warning(f"422 응답 -> 개별 키워드 fallback 시도 (원본 q='{q_value}')")
        aggregated = []
        for single in query:
            p2 = params.copy()
            p2['q'] = single.strip()
            # size를 균등 분배 (최소 1)
            p2['size'] = max(1, size // len(query))
            r2, e2 = _do_request(p2)
            if e2 or not r2 or r2.status_code != 200:
                continue
            try:
                data2 = r2.json()
                items2 = data2.get('results') or data2.get('items') or []
                aggregated.extend(items2)
            except ValueError:
                continue
        if not aggregated:
            logger.error("422 fallback 재시도에서도 기사 0건")
            return []
        items_raw = aggregated
    elif err:
        return []
    else:
        try:
            data = resp.json()
            items_raw = data.get('results') or data.get('items') or []
        except ValueError:
            logger.error("NEWS_DATA_API 응답 JSON 파싱 실패")
            return []

    validated_items = []
    for item in items_raw:
        try:
            validated_item = NewsDataItemSchema(**item)
            validated_items.append(validated_item.model_dump())
        except ValidationError:
            continue

    logger.info(f"NEWS_DATA_API 수신 성공: {len(validated_items)}개 (q={params.get('q')})")
    return validated_items

@monitor_performance(include_memory=True)
def crawl_article_with_newspaper3k(url: str) -> tuple[str | None]:
    """
    User-Agent 설정을 사용하여 기사의 제목, 본문을 추출합니다.
    
    Returns:
        tuple: (title, content) - 제목, 본문 리스트
    """
    try:
        # --- User-Agent 설정 ---
        config = Configuration()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
        config.request_timeout = 10

        # 언어는 사이트별로 상이하므로 지정하지 않아 자동 감지에 맡깁니다.
        article = NewspaperArticle(url, config=config, fetch_images=True)
        article.download()
        article.parse()

        # 제목이나 본문이 비어있는 경우 실패로 간주.
        if not article.title or not article.text:
            logger.debug(f"제목 또는 본문 추출 실패: {url}")
            return None, None

        # 본문 내용이 너무 짧으면 유효하지 않은 기사로 간주.
        if len(article.text) < 200:
            logger.info(
                f"기사 본문 길이 부족으로 건너뜀: {len(article.text)}자 (최소 200자 필요) - {url}"
            )
            return None, None

        logger.info("기사 크롤링 완료")
        return article.title, article.text

    except Exception as e:
        logger.error(
            f"newspaper3k 파싱 중 에러 발생 (URL: {url}): {e.__class__.__name__} - {e}"
        )
        return None, None
