"""
서비스 레이어의 유틸리티 함수 모음

이 모듈은 기사 생성/조회/상태 업데이트와 LLM 분석 결과를
데이터베이스에 저장하는 도우미 함수를 제공합니다.
"""

import json
from datetime import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from bs4 import BeautifulSoup
from dateutil.parser import parse

from ..models import (
    Article,
    ArticleContent,
    EnrichedArticle,
    ArticleStatus,
)

from ..models.statistic_model.statistic import (
    Indicator, Observation
)
from logs.logging_config import get_logger
logger = get_logger(__name__)


class DatabaseError(Exception):
    """데이터베이스 관련 예외를 래핑하기 위한 커스텀 예외클래스."""
    pass


class ValidationError(Exception):
    """입력값 검증 실패 시 발생시키는 예외."""
    pass


def create_article(db: Session, title: str, url: str, description: str, published_at: str, content: str, images: list[str] = None) -> Article | None:
    """새로운 Article 레코드를 생성하여 DB에 저장합니다.

    반환값: 생성된 Article 객체 또는 유효하지 않거나 중복인 경우 None을 반환.
    주요 검증:
      - title, url, content는 필수
      - content 길이가 매우 짧을 경우(예: <50) 저장하지 않음
      - 동일 URL이 이미 존재하면 중복으로 간주하고 저장하지 않음
    """
    if not title or not url or not content:
        raise ValidationError("title, url, content는 필수 입력값입니다.")
    if len(content.strip()) < 50:
        # 너무 짧은 본문은 유효하지 않음
        return None

    try:
        # 중복 URL 검사
        if db.query(Article).filter(Article.url == url).first():
            logger.debug(f"중복된 URL 발견, 건너뜀: {url}")
            return None

        # 발행일 문자열을 파싱 (유효성 검사)
        try:
            parsed_date = parse(published_at)
        except (ValueError, TypeError):
            raise ValidationError(f"날짜 형식이 올바르지 않습니다: {published_at}")

        main_image_url = images[0] if images else None

        # Article 및 ArticleContent 객체 구성
        new_article = Article(
            title=title.strip(),
            url=url.strip(),
            description=BeautifulSoup(description, "html.parser").get_text(strip=True),
            published_at=parsed_date,
            status=ArticleStatus.PENDING,
            image_url=main_image_url,
        )
        new_article.content = ArticleContent(
            content=content.strip(),
            images=images if images else [],
        )

        db.add(new_article)
        db.commit()
        db.refresh(new_article)

        logger.info(f"신규 기사 저장 완료: (ID: {new_article.id}) {new_article.title}")
        return new_article

    except SQLAlchemyError as e:
        # DB 오류 발생 시 롤백하고 커스텀 예외로 래핑
        logger.error(f"데이터베이스 오류 발생 (URL: {url}): {e}")
        db.rollback()
        raise DatabaseError(f"기사 저장 중 데이터베이스 오류가 발생했습니다.")
    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"기사 저장 중 예상치 못한 오류 발생 (URL: {url}): {e}")
        db.rollback()
        raise


def get_pending_articles(db: Session) -> list[Article]:
    """PENDING 또는 FAILED 상태의 기사 목록을 반환합니다 (처리 대상)."""
    return db.query(Article).filter(
        Article.status.in_([ArticleStatus.PENDING, ArticleStatus.FAILED])
    ).all()


def get_article_by_id(db: Session, article_id: int) -> Article | None:
    """ID로 단일 Article을 조회합니다. 없으면 None 반환."""
    return db.query(Article).filter(Article.id == article_id).first()


def update_article_status(db: Session, article: Article, status: ArticleStatus):
    """기사 상태를 업데이트하고 커밋합니다. DB 오류는 DatabaseError로 래핑됩니다."""
    try:
        article.status = status
        db.commit()
        logger.info(f"기사 ID {article.id}의 상태를 {status.value}(으)로 업데이트.")
    except SQLAlchemyError as e:
        logger.error(f"기사 ID {article.id} 상태 업데이트 중 오류 발생: {e}")
        db.rollback()
        raise DatabaseError("기사 상태 업데이트 중 데이터베이스 오류가 발생했습니다.")


def save_enriched_data_and_cleanup(db: Session, article: Article, analysis_result: dict):
    """LLM 분석 결과를 EnrichedArticle에 저장하고 Article 상태를 PROCESSED로 변경합니다.

    이 함수는 간단한 키 추출(background, keywords, category, hashtags)을 수행하고
    관련 테이블에 저장/업데이트합니다.
    """
    try:
        # analysis_result 딕셔너리에서 데이터 추출
        background_data = analysis_result.get("background_knowledge")
        keywords_data = analysis_result.get("keywords")
        category_data = analysis_result.get("category", "기타")
        hashtags = analysis_result.get("hashtags")  # list[str] | None

        # EnrichedArticle 객체 생성 및 저장
        new_enriched = EnrichedArticle(
            article_id=article.id,
            background=background_data,
            keywords=keywords_data,
            category=category_data,
            hashtags=hashtags,
        )
        db.add(new_enriched)

        # Article 테이블 업데이트
        article.category = category_data
        article.hashtags = hashtags
        article.status = ArticleStatus.PROCESSED

        db.commit()
        logger.info(f"기사 ID {article.id}의 분석 결과 저장 및 정리 완료")

    except SQLAlchemyError as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 DB 오류 발생: {e}")
        db.rollback()
        raise DatabaseError("분석 결과 저장 중 데이터베이스 오류가 발생했습니다.")
    except Exception as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 예상치 못한 오류 발생: {e}")
        db.rollback()
        raise


def get_contextual_statistics_for_article(
    db: Session,
    indicator_ids: list[str],
    article_published_at: datetime,
) -> list[dict]:
    """기사 발행일 기준으로 지표별 적절한 기간을 계산하여 시계열 관측값을 반환합니다.

    frequency에 따라 조회 기간을 동적으로 계산한 뒤 Observation을 조회하여
    프론트엔드에 전달하기 쉬운 형태로 변환합니다.
    """
    if not indicator_ids:
        return []

    # 요청된 지표들의 메타정보를 한 번에 조회
    indicators = db.query(Indicator).filter(Indicator.indicator_id.in_(indicator_ids)).all()
    indicator_meta_map = {ind.indicator_id: ind for ind in indicators}

    results = []
    end_date = article_published_at.date()

    for indicator_id in indicator_ids:
        meta = indicator_meta_map.get(indicator_id)
        if not meta:
            logger.warning(f"ID '{indicator_id}'에 해당하는 지표를 DB에서 찾을 수 없습니다.")
            continue

        # 주기에 따른 시작일 계산
        frequency = meta.frequency
        if frequency == 'D':  # 일별 -> 최근 14일
            start_date = end_date - relativedelta(days=14)
        elif frequency == 'M':  # 월별 -> 최근 12개월
            start_date = end_date - relativedelta(months=12)
        elif frequency == 'Q':  # 분기별 -> 최근 3년
            start_date = end_date - relativedelta(years=3)
        else:  # 알 수 없는 주기 -> 기본 6개월
            start_date = end_date - relativedelta(months=6)
            logger.info(f"지표 ID '{indicator_id}'의 주기가 '{frequency}'이므로 기본 기간(1년)을 적용합니다.")

        # Observation 조회
        observations = (
            db.query(Observation)
            .filter(
                Observation.indicator_id == indicator_id,
                Observation.date.between(start_date, end_date),
            )
            .order_by(Observation.date.asc())
            .all()
        )

        # 결과 구조화
        results.append({
            "indicator_id": meta.indicator_id,
            "name": meta.name,
            "unit": meta.unit,
            "notes": meta.notes,
            "frequency": meta.frequency,
            "observations": [
                {"date": obs.date.isoformat(), "value": obs.value}
                for obs in observations
            ],
        })

    return results


def save_enriched_data_and_cleanup(
    db: Session,
    article: Article,
    analysis_result: dict,
    statistics_data: list[dict],
):
    """LLM 분석 결과와 계산된 통계(시계열) 데이터를 EnrichedArticle에 저장합니다."""
    try:
        background_data = analysis_result.get("background_knowledge")
        keywords_data = analysis_result.get("keywords")
        category_data = analysis_result.get("category", "기타")
        related_stats_meta = analysis_result.get("related_statistics")
        hashtags = analysis_result.get("hashtags")  # list[str] or None

        # EnrichedArticle 객체 생성(통계 데이터 포함)
        new_enriched = EnrichedArticle(
            article_id=article.id,
            background=background_data,
            keywords=keywords_data,
            category=category_data,
            related_statistics=related_stats_meta,
            statistics_data=statistics_data,  # 새로 가공된 시계열 데이터 저장
            hashtags=hashtags,
        )
        db.add(new_enriched)

        # Article 테이블 업데이트
        article.category = category_data
        article.hashtags = hashtags
        article.status = ArticleStatus.PROCESSED

        db.commit()
        logger.info(f"기사 ID {article.id}의 분석 결과 및 통계 데이터 저장 완료")

    except SQLAlchemyError as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 DB 오류 발생: {e}")
        db.rollback()
        raise DatabaseError("분석 결과 저장 중 데이터베이스 오류가 발생했습니다.")
    except Exception as e:
        logger.error(f"기사 ID {article.id}의 분석 결과 저장 중 예상치 못한 오류 발생: {e}")
        db.rollback()
        raise