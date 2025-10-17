"""
뉴스 가이드 수집기 유틸리티

이 모듈은 외부 뉴스 API(예: 네이버) 및 newspaper3k를 사용해
기사 메타데이터와 본문/이미지를 수집하고, 기사 본문에 적합한 이미지를
선별하는 헬퍼 함수를 제공합니다.

주의: 네트워크 I/O가 포함된 함수들이 있으므로 호출 시 타임아웃/리트라이 정책을 고려하세요.
"""

import requests
from newspaper import Article as NewspaperArticle
from newspaper.configuration import Configuration
from pydantic import ValidationError
from PIL import Image
from io import BytesIO
from ..config import settings

from logs.logging_config import get_logger
from app.schemas.external import NaverNewsItemSchema
from ..monitoring import monitor_performance

logger = get_logger(__name__)

NAVER_CLIENT_ID = settings.NAVER_CLIENT_ID
NAVER_CLIENT_SECRET = settings.NAVER_CLIENT_SECRET


def _is_valid_content_image(image_url: str) -> bool:
    """기사 본문에 포함할 유효한 이미지인지 판정.

    검사 항목:
      - 빈 URL 배제
      - 광고/로고/아이콘 키워드 필터링
      - URL 기반의 크기/확장자/도메인 필터링
      - URL에 포함된 "800x600" 형태의 치수 정보로 최소 크기 추정
    """
    if not image_url:
        return False

    # 검사 편의를 위해 소문자 비교
    url_lower = image_url.lower()

    # 1) 광고/프로모션 관련 키워드 제외
    ad_keywords = [
        'banner', 'ad', 'ads', 'adv', 'advertisement', 'promo', 'promotion',
        '광고', 'popup', 'overlay', 'sidebar', 'footer', 'header',
        'logo', 'icon', 'favicon', 'profile', 'avatar', 'thumbnail_small',
        'toplogo', 'printlogo', 'downlogo', 'lightbulb', 'smiley',
        'editor/images', 'ndsoft.gif'
    ]

    if any(keyword in url_lower for keyword in ad_keywords):
        logger.debug(f"광고성 이미지로 판단되어 제외: {image_url}")
        return False

    # 2) URL에 작은 크기 단서가 있으면 제외
    size_filters = [
        'small', 'mini', 'tiny', 'thumb', '50x50', '100x100', '150x150',
        '16x16', '32x32', '64x64', 'icon'
    ]

    if any(size in url_lower for size in size_filters):
        logger.debug(f"작은 크기 이미지로 판단되어 제외: {image_url}")
        return False

    # 3) 확장자 검사
    valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
    url_without_params = image_url.split('?')[0]
    has_valid_extension = any(url_without_params.endswith(ext) for ext in valid_extensions)

    if not has_valid_extension:
        logger.debug(f"유효하지 않은 이미지 확장자로 판단되어 제외: {image_url}")
        return False

    # 4) URL에서 치수 추출 가능하면 최소치보다 큰지 확인
    import re
    size_pattern = r'(\d+)x(\d+)'
    size_match = re.search(size_pattern, url_lower)

    if size_match:
        width, height = int(size_match.group(1)), int(size_match.group(2))
        if width < 150 or height < 150:
            logger.debug(f"이미지 크기가 너무 작아 제외 ({width}x{height}): {image_url}")
            return False

    # 5) 알려진 광고 도메인 제외
    ad_domains = [
        'googleads', 'doubleclick', 'googlesyndication', 'adsystem',
        'facebook.com/tr', 'google-analytics', 'gtag', 'pixel'
    ]

    if any(domain in url_lower for domain in ad_domains):
        logger.debug(f"광고 도메인으로 판단되어 제외: {image_url}")
        return False

    return True


def _check_image_size(image_url: str, min_width: int = 200, min_height: int = 150) -> bool:
    """실제 이미지를 일부 다운로드하여 크기를 검사합니다.

    성능상 비용이 있으므로 제한적으로(예: 상위 몇 개 이미지)만 호출합니다.
    오류 발생 시 기본적으로 포함하도록 구현되어 있습니다.
    """
    try:
        response = requests.get(image_url, stream=True, timeout=5, headers={'Range': 'bytes=0-2048'})
        response.raise_for_status()

        img = Image.open(BytesIO(response.content))
        width, height = img.size

        if width >= min_width and height >= min_height:
            logger.debug(f"이미지 크기 검증 통과 ({width}x{height}): {image_url}")
            return True
        else:
            logger.debug(f"이미지 크기가 작아 제외 ({width}x{height}): {image_url}")
            return False

    except Exception as e:
        # 네트워크/파싱 오류 시에는 보수적으로 포함 (False를 반환하면 이미지가 손실될 수 있음)
        logger.debug(f"이미지 크기 검증 실패, 포함함: {image_url} - {e}")
        return True


@monitor_performance(include_memory=True)
def call_naver_api(query: str, display: int = 3) -> list:
    """네이버 뉴스 Open API를 호출하여 검증된 기사 메타 리스트를 반환합니다."""
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
                # 스키마 검증을 통해 필수 필드가 있는지 확인
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
def crawl_article_with_newspaper3k(url: str) -> tuple[str | None, str | None, list[str] | None]:
    """newspaper3k를 사용해 기사 제목, 본문, 이미지 리스트를 추출합니다."""
    try:
        # --- User-Agent 설정 ---
        config = Configuration()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'
        config.request_timeout = 10

        article = NewspaperArticle(url, language='ko', config=config, fetch_images=True)
        article.download()
        article.parse()

        # 제목/본문 누락 시 실패로 처리
        if not article.title or not article.text:
            logger.debug(f"제목 또는 본문 추출 실패: {url}")
            return None, None, None

        # 본문 길이 필터(너무 짧으면 유효하지 않음)
        if len(article.text) < 200:
            logger.info(f"기사 본문 길이 부족으로 건너뜀: {len(article.text)}자 (최소 200자 필요) - {url}")
            return None, None, None

        images = []
        if article.top_image and _is_valid_content_image(article.top_image):
            images.append(article.top_image)

        if hasattr(article, 'images') and article.images:
            filtered_images = []
            for img in article.images:
                if (img and img not in images and (img.startswith('http') or img.startswith('https')) and _is_valid_content_image(img)):
                    # 성능 상 첫 3개 이미지만 실제 크기 검증 수행
                    if len(filtered_images) < 3:
                        if _check_image_size(img):
                            filtered_images.append(img)
                    else:
                        filtered_images.append(img)

            images.extend(filtered_images[:4])  # 최대 5개(메인 포함)

        logger.info(f"기사 크롤링 완료: {len(images)}개 이미지 추출 - {url}")
        return article.title, article.text, images

    except Exception as e:
        logger.error(f"newspaper3k 파싱 중 에러 발생 (URL: {url}): {e.__class__.__name__} - {e}")
        return None, None, None
