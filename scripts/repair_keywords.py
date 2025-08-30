# repair_keywords.py
# 데이터베이스 domain_terms 테이블 내용 최신 업데이트 스크립트
import json
import sys
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from tqdm import tqdm

# 프로젝트 루트를 Python 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# --- 프로젝트 모듈 임포트 ---
from app.database import SessionLocal
from app.models import EnrichedArticle, DomainTerm

# .env 파일 로드 (프로젝트 루트에서)
os.chdir(project_root)
load_dotenv()

def repair_keywords_format():
    """
    enriched_articles 테이블의 keywords 컬럼에 있는 요약문을
    domain_terms 테이블의 최신 요약문으로 업데이트합니다.
    """
    db = SessionLocal()
    try:
        print("enriched_articles 테이블의 모든 데이터를 불러옵니다...")
        all_enriched_articles = db.query(EnrichedArticle).all()

        if not all_enriched_articles:
            print("복구할 데이터가 없습니다.")
            return

        print(f"총 {len(all_enriched_articles)}개의 데이터 복구를 시작합니다.")
        
        for enriched in tqdm(all_enriched_articles, desc="키워드 형식 복구 중"):
            try:
                keyword_data_list = json.loads(enriched.keywords)
                if not isinstance(keyword_data_list, list):
                    continue
            except (json.JSONDecodeError, TypeError):
                print(f"Article ID {enriched.article_id}의 키워드 파싱 실패. 건너뜁니다.")
                continue

            new_keywords_data = []
            for keyword_item in keyword_data_list:
                term_str = None
                # --- 🔽 (수정) 키워드 항목이 딕셔너리인지 문자열인지 확인 ---
                if isinstance(keyword_item, dict):
                    term_str = keyword_item.get('term') # 딕셔너리에서 'term' 값 추출
                elif isinstance(keyword_item, str):
                    term_str = keyword_item # 이전 형식(문자열)도 처리

                if not term_str:
                    continue

                # 'term' 문자열을 사용해 DB에서 최신 정보를 조회
                domain_term = db.query(DomainTerm).filter(DomainTerm.term == term_str).first()
                if domain_term:
                    new_keywords_data.append({
                        "term": domain_term.term,
                        "summary": domain_term.summary
                    })
            
            if new_keywords_data:
                enriched.keywords = json.dumps(new_keywords_data, ensure_ascii=False)

        print("모든 변경사항을 데이터베이스에 저장합니다...")
        db.commit()
        print("데이터 복구가 성공적으로 완료되었습니다!")

    except Exception as e:
        print(f"복구 중 에러 발생: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    repair_keywords_format()
