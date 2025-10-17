import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from app.core.news_guide import collectors, processors
except ModuleNotFoundError:
    from fin_sight_server.app.core.news_guide import collectors, processors

from dotenv import load_dotenv
from tqdm import tqdm
import requests
from openai import OpenAIError

from app.database import SessionLocal
from app.models import ArticleStatus
from app.core import services
from logs.logging_config import get_logger

load_dotenv()
logger = get_logger(__name__)


"""
파일: scripts/news/pipeline.py
목적: 기사 수집 → LLM 기반 분석 → EnrichedArticle 저장의 전체 파이프라인 실행 스크립트

Usage:
    # 로컬에서 간단 실행
    python scripts/news/pipeline.py

필수 환경변수(예시):
    - OPENAI_API_KEY: OpenAI/LLM 접근 키
    - NAVER_CLIENT_ID / NAVER_CLIENT_SECRET: 네이버 검색 API 사용 시 필요
    - DATABASE_URL: PostgreSQL 연결 URL

주의 및 재현 팁:
    - 실제 배포/대량 실행 시 rate-limit, API quota에 유의하세요.
    - .env 파일에 필요한 값들을 설정한 뒤 실행하면 됩니다. (비밀 키는 절대 소스에 하드코딩 금지)
"""


def run_article_processing_pipeline():
    """전체 기사 처리 파이프라인 실행.

    반환값: 없음 (DB에 결과 저장)

    구현 노트:
      - 1단계는 외부 API(네이버)와 크롤러 의존이 있으므로 네트워크 실패에 대비해 예외를 잡아 넘어갑니다.
      - 2단계에서 LLM 호출 결과를 기반으로 추가 컨텍스트(연관 통계)를 조회하여 함께 저장합니다.
    """
    db = SessionLocal()
    try:
        # --- 1단계: 신규 기사 수집 및 원문 저장 (기존과 동일) ---
        logger.info("\n--- 1단계: 신규 기사 수집 시작 ---")
        #search_keywords = ["금리", "주식", "부동산", "채권", "물가", "환율", "경제성장률", "수출"]
        search_keywords = ["관세", "미국"]  # 테스트용

        # 각 키워드에 대해 네이버 API 호출 후 기사 원문을 크롤링하여 DB에 저장
        for keyword in tqdm(search_keywords, desc="키워드별 기사 수집"):
            try:
                raw_articles_meta = collectors.call_naver_api(query=keyword, display=5)
                for meta in raw_articles_meta:
                    url = str(meta['originallink'])

                    title, content, images = collectors.crawl_article_with_newspaper3k(url)

                    # 본문 길이가 매우 짧으면 유의미한 분석이 어려우므로 건너뜀
                    if not content or len(content) < 200:
                        logger.warning(f"콘텐츠가 너무 짧거나 없어서 수집을 건너뜁니다: {url}")
                        continue

                    services.create_article(
                        db=db,
                        title=title,
                        url=url,
                        description=meta['description'],
                        published_at=meta['pubDate'],
                        content=content,
                        images=images,
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"네이버 API 호출 실패 (키워드: {keyword}): {e}")
                continue
        logger.info("--- 1단계: 신규 기사 수집 완료 ---\n")

        # --- 2단계: 처리 대기 중인 기사 가공 ---
        pending_articles = services.get_pending_articles(db)
        logger.info(f"--- 2단계: 총 {len(pending_articles)}개의 기사 처리 시작 ---")

        # 대기 중 기사들을 순회하며 LLM 분석 및 부가 데이터 조회/저장 수행
        for article in tqdm(pending_articles, desc="기사 가공 처리"):
            try:
                # 2-1. 상태를 'PROCESSING'으로 변경
                services.update_article_status(db, article, ArticleStatus.PROCESSING)

                # 2-2. LLM을 사용한 기사 분석 (DB 세션 전달)
                full_content = article.content.content
                # LLM 분석 수행 (DB 세션을 전달하여 prompt/context 조회에 사용 가능)
                analysis_result = processors.analyze_article_with_llm(db=db, content=full_content)

                if not analysis_result or "background_knowledge" not in analysis_result or "category" not in analysis_result:
                    raise ValueError("LLM으로부터 유효한 기본 분석 응답을 받지 못했습니다.")

                # --- (추가) 2-3. LLM이 식별한 ID로 시계열 데이터 조회 ---
                related_ids = [
                    item['indicator_id']
                    for item in analysis_result.get("related_statistics", [])
                    if item.get('indicator_id')
                ]

                # LLM이 제안한 관련 지표들에 대해 시계열 데이터를 조회
                final_stats_data = []
                if related_ids:
                    logger.info(f"기사 ID {article.id}: LLM이 관련 지표 {related_ids}를 식별했습니다. 시계열 데이터를 조회합니다.")
                    final_stats_data = services.get_contextual_statistics_for_article(
                        db=db,
                        indicator_ids=related_ids,
                        article_published_at=article.published_at,
                    )

                # --- (수정) 2-4. 최종 결과 저장 ---
                services.save_enriched_data_and_cleanup(db, article, analysis_result, final_stats_data)
                logger.info(f"기사 ID {article.id} 처리 성공.")

            except (requests.exceptions.RequestException, OpenAIError) as api_error:
                logger.error(f"기사 ID {article.id} 처리 중 API 오류 발생: {api_error}")
                db.rollback()
                article_to_fail = services.get_article_by_id(db, article.id)
                if article_to_fail:
                    services.update_article_status(db, article_to_fail, ArticleStatus.FAILED)

            except ValueError as data_error:
                logger.warning(f"기사 ID {article.id} 처리 중 데이터 오류 발생: {data_error}")
                db.rollback()
                article_to_fail = services.get_article_by_id(db, article.id)
                if article_to_fail:
                    services.update_article_status(db, article_to_fail, ArticleStatus.FAILED)

            except Exception as e:
                logger.critical(f"\n기사 ID {article.id} 처리 중 예상치 못한 심각한 오류 발생: {e}", exc_info=True)
                db.rollback()
                article_to_fail = services.get_article_by_id(db, article.id)
                if article_to_fail:
                    services.update_article_status(db, article_to_fail, ArticleStatus.FAILED)
                continue

        logger.info(f"--- 2단계: 기사 처리 완료 ---")

    finally:
        db.close()


if __name__ == "__main__":
    run_article_processing_pipeline()
