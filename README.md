# FinSight Server

금융 뉴스 수집·분석 API 서버(FastAPI 기반). 이 문서는 현재 코드에 근거해 실제로 존재하는 기능과 운영 방법만을 정리합니다.

## 목차

- [주요 기능](#주요-기능)
- [아키텍처](#아키텍처)
- [프로젝트 구조(요약)](#프로젝트-구조요약)
- [요구 사항](#요구-사항)
- [시작하기](#시작하기)
- [Docker/Compose](#dockercompose)
- [데이터 파이프라인](#데이터-파이프라인)
- [API 개요](#api-개요)
- [보안/운영 참고](#보안운영-참고)
- [CI/CD(요약)](#cicd요약)
- [트러블슈팅](#트러블슈팅)
- [라이선스](#라이선스)

## 주요 기능

- FastAPI 기반 REST API 제공
- PostgreSQL + SQLAlchemy + Alembic 마이그레이션
- Prometheus 메트릭(`/metrics`) 노출 및 기본 시스템 메트릭 로깅
- Docker/Docker Compose 및 GitHub Actions 기반 배포 파이프라인

## 아키텍처

아래는 시스템 아키텍처 개요입니다. 운영 환경에서는 EC2 상의 Docker 컨테이너에서 애플리케이션을 구동하고, 데이터베이스는 Amazon RDS(PostgreSQL)를 사용합니다.

![Architecture](docs/serverArchitecture.png)



## 프로젝트 구조(요약)

```
fin_sight_server/
├── app/
│   ├── api/
│   │   ├── health.py         # /health 헬스체크(API+DB)
│   │   ├── articles.py       # 기사 조회/검색 + 관리자 엔드포인트
│   │   └── letters.py        # 뉴스레터(초안/배치) 조회/발행
│   ├── core/
│   │   ├── config.py         # 설정 로딩(.env 우선순위)
│   │   └── monitoring.py     # 성능/시스템 메트릭 유틸
│   ├── models/               # ORM 모델
│   ├── schemas/              # Pydantic 스키마
│   ├── database.py           # DB 엔진/세션 + get_db
│   └── main.py               # FastAPI 앱, CORS, /metrics, 라우터 등록
├── alembic/                  # DB 마이그레이션
├── Dockerfile
├── docker-compose.yml        # 모니터링 스택(prometheus/grafana/node-exporter)
├── docker-compose.prod.yml   # 앱+DB(+옵션: 모니터링) 운영용 compose
├── prometheus.yml            # Prometheus 스크레이프 설정
├── requirements.txt          # 의존성 목록
├── pyproject.toml            # 패키징/의존성 메타
└── .github/workflows/deploy.yml  # Docker 빌드/EC2 배포
```

## 요구 사항

- Python 3.10+
- PostgreSQL 15 (또는 호환 버전)
- pip, virtualenv(선택)

## 시작하기

1) 의존성 설치

```bash
cd fin_sight_server
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

2) 환경 변수 설정

`app/core/config.py`는 다음 우선순위로 설정 파일을 로드합니다.

1. ENV_FILE 환경변수로 지정된 경로
2. ./.env
3. ./.env.dev
4. ./.env.prod (기본값은 .env.dev)

필수/주요 항목(예시 형식만 제시, 값은 환경에 맞게 설정):

샘플 복사(로컬 개발):

```bash
cp .env.example .env
# 이후 .env 파일을 열어 각 값을 채워 넣으세요.
```

```env
# Database
DATABASE_URL=postgresql://USER:PASS@HOST:5432/DBNAME

# External APIs
OPENAI_API_KEY=...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
ECOS_API_KEY=...
NEWS_DATA_API_KEY=...

# App
DEBUG=true
LOG_LEVEL=INFO

# (옵션)
REDIS_URL=
ADMIN_API_KEY=  # 관리자 엔드포인트 보호용 헤더 값(추후 업데이트 예정)
UNSAFE_ADMIN_MODE=0  # 1이면 관리자 인증 우회(로컬 개발 한정)

# 파이프라인/LLM 관련 설정(코드 참조)
BATCH_SIZE=
MAX_WORKERS=
RETRY_ATTEMPTS=
LLM_MODEL=
MAX_TOKENS=
TEMPERATURE=
```

3) 데이터베이스 마이그레이션

```bash
alembic upgrade head
```

4) 개발 서버 실행

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

접근 포인트:
- OpenAPI 문서: http://localhost:8000/docs (또는 /redoc)
- 헬스체크: http://localhost:8000/health
- 메트릭: http://localhost:8000/metrics

## Docker/Compose

- 단일 컨테이너(이미지) 실행은 Dockerfile + `docker-entrypoint.sh`를 사용합니다.
- 로컬 모니터링 스택: `docker-compose.yml` (prometheus, grafana, node-exporter)
- 운영용: `docker-compose.prod.yml` (app + db, 모니터링은 `profiles: ["monitoring"]`로 선택)
	- 실제 운영에서는 RDS(PostgreSQL)를 사용하며, `DATABASE_URL`을 RDS 엔드포인트로 오버라이드하여 내부 `db` 서비스 없이 구동합니다.

예) 운영 compose 기동(예시)

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 데이터 파이프라인

파이프라인 스크립트는 `scripts/` 하위에 위치합니다. 아래는 실제 스크립트 기준의 간단 실행 예시이며, 상세한 사용법/운영 절차는 문서 링크를 참고하세요.

### 1) 뉴스 수집·분석
- 경로: `scripts/news/pipeline.py`
- 동작: 네이버 검색 → 기사 크롤링 → 본문 길이 필터 → Article 저장 → PENDING 기사 LLM 분석 → Enriched 데이터 저장(관련 통계 조회 포함)
- 필요 환경: `OPENAI_API_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `DATABASE_URL`

```bash
python scripts/news/pipeline.py
```

자세히: [docs/news_pipeline.md](docs/news_pipeline.md)

### 2) ECOS 경제지표
- 카탈로그 반영: 카탈로그 JSON을 지표 테이블에 반영(+옵션: 상태 테이블 부트스트랩)

```bash
# 기본 카탈로그 반영
python scripts/ecos/ingest_catalog.py --bootstrap-state

# 새 카탈로그 파일 사용 + 상태 강제 초기화(주의)
python scripts/ecos/ingest_catalog.py --file data/catalog_core15.json --bootstrap-state --force-state
```

- 증분 수집: 최근 구간 재검증(rewind) 옵션으로 누락값 보정

```bash
python scripts/ecos/ingest_ecos_incremental.py --recheck-days 7
```

- 내보내기(백업/전달): 관측치 JSONL 생성(카탈로그 기반 또는 전체)

```bash
# 특정 지표만
python scripts/ecos/export_observations_core.py --only kr.cpi.headline.m kr.ppi.m

# 전체
python scripts/ecos/export_observations_core.py --all
```

자세히: [docs/data_pipeline.md](docs/data_pipeline.md)

### 3) 레터(섹터/회사) 아웃라인
- 경로: `scripts/letter/run_sector.py`
- 동작: (sector,key) 구성 기반 뉴스 수집/크롤링 → LLM으로 아웃라인 생성 → DB 저장. `--fresh`로 강제 재생성. `--list`/`--show-config` 제공.
- 필요 환경: `OPENAI_API_KEY`, `DATABASE_URL` 등

```bash
# 사용 가능한 (sector,key) 목록
python scripts/letter/run_sector.py --list

# 섹터 설정 보기
python scripts/letter/run_sector.py --show-config macro

# 실행 예시
python scripts/letter/run_sector.py --sector market --key us_market --size 18
```

자세히: [docs/letter_pipeline.md](docs/letter_pipeline.md)

## API 개요

헬스/루트
- GET `/` — 단순 서버 상태 메시지
- GET `/health` — 서버 및 DB 연결 확인(SELECT 1)

기사(Articles) — prefix: `/api/articles`
- GET `/today` — 최근 처리완료(PROCESSED) 기사 목록 (페이지네이션: skip, limit)
- GET `/category/{category}` — 카테고리별 기사 목록
- GET `/search?q=...` — 제목/설명/해시태그 부분 일치 검색
- GET `/{article_id}` — 기사 상세(EnrichedArticle 포함 정보 조합)

관리자(Admin) — prefix: `/api/articles/admin` (헤더 `X-ADMIN-KEY` 필요)
- DELETE `/{article_id}` — 소프트 삭제(플래그 처리 + 잠금 시간)
- POST `/{article_id}/restore` — 소프트 삭제 복구
- DELETE `/{article_id}/purge` — 영구 삭제(잠금 기한 경과 필요)

뉴스레터(Letters) — prefix: `/api/letters`
- GET `/{sector}/{key}` — 최신 배치의 초안(Outline) 조회
- GET `/{sector}/{key}/history` — 배치 이력 목록 조회
- POST `/{sector}/{key}/{batch_id}/publish` — 특정 배치 발행 처리(status=delivered)

메트릭
- GET `/metrics` — Prometheus 포맷 메트릭 노출

## 보안/운영 참고

- 관리자 엔드포인트 접근은 `X-ADMIN-KEY` 헤더를 사용합니다. 값은 `ADMIN_API_KEY` 환경변수로 주입하세요.
- 로컬 개발 편의를 위해 `UNSAFE_ADMIN_MODE=1`이면 관리자 인증이 우회됩니다(실제 운영에는 비권장).
- `app/main.py`에서 CORS 허용 오리진이 화이트리스트로 설정되어 있습니다(본인 환경에 맞게 조정 권장).
- `/metrics`는 기본 Instrumentator 설정으로 노출됩니다. 필요 시 라벨/카디널리티 정책을 조정하세요.

## CI/CD(요약)

`.github/workflows/deploy.yml`
- main 브랜치 푸시 시 Docker 이미지 빌드/푸시
- 이후 EC2에 SSH로 접속해 컨테이너 교체 실행(`--env-file prod.env` 등)

## 트러블슈팅

- 데이터베이스 연결 오류: `DATABASE_URL` 확인 후 `/health`에서 `database: connected` 여부 확인
- 마이그레이션 실패: `alembic current` / `alembic history`로 상태 확인 → 충돌 시 정리 후 재시도
- 메트릭 수집 불가: Prometheus 타깃/metrics_path 확인(`prometheus.yml`)

## 라이선스
개인 프로젝트
