# scripts/seed_statistics.py

import json
import os
import sys
from tqdm import tqdm
from sqlalchemy.dialects.postgresql import insert

# --- 프로젝트 경로 설정 ---
# 이 스크립트가 다른 모듈을 임포트할 수 있도록 프로젝트 루트를 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# --- 프로젝트 모듈 임포트 ---
from app.database import SessionLocal
from app.models.statistic_model.statistic import Indicator, Observation
from logs.logging_config import get_logger

logger = get_logger(__name__)

# --- 상수 정의 ---
DATA_DIR = os.path.join(project_root, 'data')
INDICATORS_FILE = os.path.join(DATA_DIR, 'catalog_core15.json')
OBSERVATIONS_FILE = os.path.join(DATA_DIR, 'observations_core15.jsonl')
BATCH_SIZE = 10000  # 한 번에 DB에 삽입할 데이터 수

def seed_statistics_data():
    """
    JSON 파일로부터 통계 데이터를 읽어와 DB에 저장하는 메인 함수
    """
    db = SessionLocal()
    try:
        # --- 1단계: Indicator 메타데이터 삽입 ---
        logger.info(f"'{INDICATORS_FILE}'에서 지표 메타데이터를 로드합니다.")
        with open(INDICATORS_FILE, 'r', encoding='utf-8') as f:
            indicators_meta = json.load(f)

        for meta in tqdm(indicators_meta, desc="지표 메타데이터 저장 중"):
            
            if not meta.get("name"):
                logger.warning(f"지표 ID '{meta['indicator_id']}'의 이름이 없어 건너뜁니다.")
                continue
            
            indicator = Indicator(
                indicator_id=meta["indicator_id"],
                name=meta["name"],
                frequency=meta.get("frequency"),
                unit=meta.get("unit"),
                source=meta.get("source"),
                notes=meta.get("notes"),
                stat_code=meta.get("stat_code"),
                item_code1=meta.get("item_code1"),
                item_code2=meta.get("item_code2"),
                item_code3=meta.get("item_code3"),
                item_code4=meta.get("item_code4")
            )
            db.merge(indicator) # Primary Key 기준으로 없으면 INSERT, 있으면 UPDATE
        db.commit()
        logger.info("지표 메타데이터 저장 완료.")

        # --- 2단계: Observation 시계열 데이터 삽입 ---
        logger.info(f"'{OBSERVATIONS_FILE}'에서 시계열 데이터를 로드하여 저장합니다.")
        
        observations_batch = []
        with open(OBSERVATIONS_FILE, 'r', encoding='utf-8') as f:
            for line in tqdm(f, desc="시계열 데이터 처리 중"):
                data = json.loads(line)
                
                # SQLAlchemy 모델에 맞는 딕셔너리만 추출
                observation_dict = {
                    "indicator_id": data["indicator_id"],
                    "date": data["date"],
                    "value": data["value"]
                }
                observations_batch.append(observation_dict)

                # 배치 사이즈에 도달하면 DB에 삽입
                if len(observations_batch) >= BATCH_SIZE:
                    stmt = insert(Observation).values(observations_batch)
                    stmt = stmt.on_conflict_do_nothing(index_elements=['indicator_id', 'date'])
                    db.execute(stmt)
                    observations_batch.clear()

            # 루프 종료 후 남은 데이터 삽입
            if observations_batch:
                stmt = insert(Observation).values(observations_batch)
                stmt = stmt.on_conflict_do_nothing(index_elements=['indicator_id', 'date'])
                db.execute(stmt)

        db.commit()
        logger.info("모든 시계열 데이터 저장 완료.")
        logger.info("통계 DB 구축이 성공적으로 완료되었습니다.")

    except FileNotFoundError as e:
        logger.error(f"데이터 파일을 찾을 수 없습니다: {e.filename}")
        db.rollback()
    except Exception as e:
        logger.critical(f"DB 구축 중 예상치 못한 오류 발생: {e}", exc_info=True)
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_statistics_data()