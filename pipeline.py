from dotenv import load_dotenv
from tqdm import tqdm
import kss
import numpy as np
import requests
from openai import OpenAIError

from app.database import SessionLocal
from app.models import ArticleStatus
from app.core import collectors, processors, services
from logs.logging_config import get_logger

load_dotenv()
logger = get_logger(__name__)

def run_article_processing_pipeline():
    """
    전체 기사 처리 파이프라인을 실행하는 메인 함수
    """
    db = SessionLocal()
    try:
        # --- 1단계: 기사 수집 및 원문 저장 ---
        logger.info("\n--- 1단계: 신규 기사 수집 시작 ---")
        #search_keywords = ["금리", "주식", "부동산", "채권", "코인", "가상자산", "펀드", "ETF", "경제지표", "환율"]
        search_keywords = ["경제지표"] #테스트 키워드

        for keyword in tqdm(search_keywords, desc="키워드별 기사 수집"):
            try:
                raw_articles_meta = collectors.call_naver_api(query=keyword, display=5)
                for meta in raw_articles_meta:
                    url = str(meta['originallink'])
                
                    # collectors가 제목과 본문을 튜플로 반환
                    title, content = collectors.crawl_article_with_newspaper3k(url)
                
                    # 크롤링 실패했거나 본문이 너무 짧으면 건너뛰기
                    if not content or len(content) < 200:
                        logger.warning(f"콘텐츠가 너무 짧거나 없어서 수집을 건너뜁니다: {url}")
                        continue
                
                    # services를 통해 DB에 저장
                    services.create_article(
                        db=db,
                        title=title,
                        url=url,
                        description=meta['description'],
                        published_at=meta['pubDate'],
                        content=content
                    )
            except requests.exceptions.RequestException as e:
                logger.error(f"네이버 API 호출 실패: {e}")
                continue
        logger.info("--- 1단계: 신규 기사 수집 완료 ---\n")

        # --- 2단계 ~ 8단계: 처리 대기 중인 기사 가공 ---
        pending_articles = services.get_pending_articles(db)
        logger.info(f"--- 2-8단계: 총 {len(pending_articles)}개의 기사 처리 시작 ---")
        
        for article in tqdm(pending_articles, desc="기사 가공 처리"):
            try:
                # 2-1. 상태를 'PROCESSING'으로 변경
                services.update_article_status(db, article, ArticleStatus.PROCESSING)

                # 2-2. 문장 분리
                full_content = article.content.content
                sentences = kss.split_sentences(full_content)
                valid_sentences = [s for s in sentences if len(s.strip()) >= 10]
                
                if not valid_sentences:
                    raise Exception("유효한 문장을 찾을 수 없습니다.")

                # 2-3. 문장 일괄 임베딩 (최적화)
                embeddings = processors.get_embeddings_in_batch(valid_sentences)
                if not embeddings or len(embeddings) != len(valid_sentences):
                    raise Exception("문장 임베딩에 실패했습니다.")
                
                # 2-4. 임시 문장 데이터 저장
                sentence_objects = services.save_sentences_and_get_objects(db, article.id, valid_sentences, embeddings)

                # 3. 핵심 문장 추출
                core_sentences = processors.extract_core_sentences(sentence_objects)

                # 4. 핵심 용어 추출 (요약문 포함)
                centroid_vector = np.mean(np.array([s.embedding for s in sentence_objects]), axis=0).tolist()
                top_terms_with_summary = services.find_top_similar_terms(db, centroid_vector)
                
                if not top_terms_with_summary:
                    raise Exception("유사한 도메인 용어를 찾지 못했습니다.")
                
                # 5. LLM 분석 요청 (토큰 최적화: 용어의 'term'만 전달)
                term_only_list = [term for term, summary in top_terms_with_summary]
                enriched_data = processors.get_enrichment_from_llm(core_sentences, term_only_list)
                
                if not enriched_data or "background" not in enriched_data or "category" not in enriched_data:
                    raise Exception("LLM으로부터 유효한 응답을 받지 못했습니다.")

                # 6. 최종 결과 저장 및 정리
                services.save_enriched_data_and_cleanup(db, article, enriched_data, top_terms_with_summary)
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
                # 롤백 후에는 article 객체가 만료되므로 다시 조회해서 상태 업데이트
                article_to_fail = services.get_article_by_id(db, article.id)
                if article_to_fail:
                    services.update_article_status(db, article_to_fail, ArticleStatus.FAILED)
                continue
        
        logger.info(f"--- 2-8단계: 기사 처리 완료 ---")

    finally:
        db.close()

if __name__ == "__main__":
    run_article_processing_pipeline()
