# domain_terms 테이블에 금융 용어 데이터를 임베딩하여 저장하는 스크립트
import json
import os
import sys
import time
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy.orm import Session
from tqdm import tqdm

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from app.database import SessionLocal
from app.models import DomainTerm

# --- 환경 설정 및 OpenAI 클라이언트 준비 ---

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise ValueError("'.env' 파엘에 OPENAI_API_KEY 환경 변수가 설정되어 있지 않습니다.")
client = OpenAI(api_key=OPENAI_API_KEY)

# --- 함수 정의 ---

def get_embedding(text: str, model="text-embedding-3-small"):
    """
    용어의 정의를 OpenAI 임베딩 모델을 사용해 백터로 변환
    """
    text = text.replace("\n", " ")
    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        print(f"OpenAI API 호출 중 에러 발생: {e}")
        # API 과부화 등을 대비해 잠시 대기 후 재시도
        time.sleep(5)
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding

def seed_domain_terms():
    """
    JSON 파일을 읽어 각 용어를 임베딩하고 DB에 저장하는 메인 함수
    """
    db = SessionLocal()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    data_directory = os.path.join(project_root, 'data')
    json_filename = 'finance_terms_700_all.json'
    json_file_path = os.path.join(data_directory, json_filename)

    try:
        print(f"'{json_file_path}' 파일에서 용어 데이터를 불러옵니다...")
        with open(json_file_path, 'r', encoding='utf-8') as f:
            terms_data = json.load(f)
        print(f"총 {len(terms_data)}개의 용어 데이터를 불러왔습니다.")

        for term_data in tqdm(terms_data, desc="용어 사전 임베딩 및 저장 중"):
            # DB에 이미 해당 용어가 있는지 확인하여 중복 저장 방지
            existing_term = db.query(DomainTerm).filter(DomainTerm.term == term_data['term']).first()
            if existing_term:
                continue

            # 'definition' 필드가 비어있는 경우 대비
            if not term_data.get('definition'):
                print(f"경고: '{term_data['term']}' 용어의 definition이 비어있어 건너뜁니다.")
                continue

            # 용어의 'definition'을 백터로 변환
            embedding_vector = get_embedding(term_data['definition'])

            # DB에 저장할 domain_term 객체 생성
            new_term = DomainTerm(
                term=term_data['term'],
                definition=term_data['definition'],
                summary=term_data.get('summary'),
                embedding=embedding_vector
            )

            # 세션에 추가
            db.add(new_term)
        
        # --- 최종 커밋 ---
        print("데이터베이스에 모든 변경사항을 저장합니다...")
        db.commit()
        print("용어 사전 데이터베이스 구축이 성공적으로 완료되었습니다.")

    except FileNotFoundError:
        print(f"에러: '{json_file_path}' 파일을 찾을 수 없습니다.")
    except Exception as e:
        print(f"예상치 못한 에러가 발생했습니다: {e}")
        print("진행 상황을 모두 롤백합니다.")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_domain_terms()