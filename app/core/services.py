import json
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from bs4 import BeautifulSoup
from dateutil.parser import parse

from app.models import Article, ArticleContent, ArticleSentence, EnrichedArticle, ArticleStatus, DomainTerm, Topic

from logs.logging_config import get_logger
logger = get_logger(__name__)

def create_article(db: Session, title: str, url: str, description: str, published_at: str, content: str) -> Article | None:
    """
    수집된 데이터를 Article 및 ArticleContent 테이블에 저장.
    URL을 기준으로 중복을 체크.
    """
    if db.query(Article).filter(Article.url == url).first():
        logger.debug(f"중복된 URL 발견, 건너뜀: {url}")
        return None
    
    try:
        new_article = Article(
        title = title,
        url = url,
        description = BeautifulSoup(description, "html.parser").get_text(strip=True),
        published_at = parse(published_at),
        status = ArticleStatus.PENDING
        )

        new_article.content = ArticleContent(content=content)

        db.add(new_article)
        db.commit()
        db.refresh(new_article)

        logger.info(f"신규 기사 저장 완료: (ID: {new_article.id}) {new_article.title}")
        return new_article
    except Exception as e:
        logger.error(f"기사 저장 중 오류 발생 (URL: {url}): {e}")
        db.rollback()
        return None

def get_pending_articles(db: Session) -> list[Article]:
    """
    'PENDING' 상태의 기사 목록을 조회.
    """
    return db.query(Article).filter(Article.status == ArticleStatus.PENDING).all()

def get_article_by_id(db: Session, article_id: int) -> Article | None:
    """
    ID로 특정 기사를 조회. (오류 처리 시 사용)
    """
    return db.query(Article).filter(Article.id == article_id).first()

def update_article_status(db: Session, article: Article, status: ArticleStatus):
    """
    기사의 상태(status)를 업데이트.
    """
    try:
        article.status = status
        db.commit()
        logger.info(f"기사 ID {article.id}의 상태를 {status.value}(으)로 업데이트.")
    except Exception as e:
        logger.error(f"기사 ID {article.id} 상태 업데이트 중 오류 발생: {e}")
        db.rollback()

def save_sentences_and_get_objects(db: Session, article_id: int, sentences: list[str], embeddings: list[list[float]]) -> list[ArticleSentence]:
    """
    문장과 임베딩 벡터를 ArticleSentence 테이블에 저장하고, 저장된 객체들을 반환.
    """
    try:
        sentence_objects = []
        for i, (sent, emb) in enumerate(zip(sentences, embeddings)):
            sentence_obj = ArticleSentence(
                article_id=article_id,
                idx=i,
                sentence=sent,
                embedding=emb
            )
            sentence_objects.append(sentence_obj)
        
        if sentence_objects:
            db.add_all(sentence_objects)
            db.commit()

        logger.info(f"기사 ID {article_id}에 대한 {len(sentence_objects)}개의 문장을 저장했습니다.")
        return db.query(ArticleSentence).filter(ArticleSentence.article_id == article_id).order_by(ArticleSentence.idx).all()
    except Exception as e:
        logger.error(f"기사 ID {article_id}의 문장 저장 중 오류 발생: {e}")
        db.rollback()
        return []
    
def find_top_similar_terms(db: Session, centroid_vector: list[float], limit: int = 4) -> list[tuple[str, str]]:
    """
    센트로이드 벡터와 가장 유사한 도메인 용어와 요약문을 DB에서 찾습.
    """
    try:
        query = text("SELECT term, summary FROM domain_terms ORDER BY embedding <=> :centroid LIMIT :limit")
        result = db.execute(query, {"centroid": str(centroid_vector), "limit": limit})
    
        return [(row[0], row[1]) for row in result]
    except Exception as e:
        logger.error(f"도메인 용어 조회 중 오류 발생: {e}")
        return []

def save_enriched_data_and_cleanup(db: Session, article: Article, enriched_data: dict, top_terms_with_summary: list[tuple[str, str]]):
    """
    최종 분석 결과를 저장하고, 상태를 업데이트하며, 임시 데이터를 정리.
    """
    try:
        # enriched_articles 테이블에 저장할 데이터 포맷팅
        keywords_to_save = [
            {"term": term, "summary": summary} for term, summary in top_terms_with_summary
        ]

        new_enriched = EnrichedArticle(
            article_id=article.id,
            background=json.dumps(enriched_data.get("background"), ensure_ascii=False),
            keywords=json.dumps(keywords_to_save, ensure_ascii=False),
            category=enriched_data.get("category", "기타")
        )
        db.add(new_enriched)

        # articles 테이블 업데이트
        article.category = new_enriched.category
        article.status = ArticleStatus.PROCESSED
    
        # 임시 문장 데이터 삭제
        db.query(ArticleSentence).filter(ArticleSentence.article_id == article.id).delete()
    
        db.commit()
        logger.info(f"기사 ID {article.id}의 분석 결과 저장 및 정리 완료")
    
    except Exception as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 오류 발생: {e}")
        db.rollback()