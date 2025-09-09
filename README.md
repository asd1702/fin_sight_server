# FinSight Server

**금융 뉴스 수집 및 분석 시스템**

FinSight는 한국의 금융 뉴스를 자동으로 수집하고, AI를 활용하여 분석하는 종합적인 데이터 파이프라인 시스템입니다.

## 🎯 주요 기능

- **실시간 뉴스 수집**: 네이버 뉴스 API를 통한 금융 관련 뉴스 자동 수집
- **AI 기반 분석**: OpenAI를 활용한 뉴스 내용 분석 및 카테고리 분류
- **경제 지표 연동**: 한국은행 ECOS API를 통한 경제 지표 데이터 수집
- **REST API**: FastAPI 기반의 웹 API 서버
- **모니터링**: Prometheus와 Grafana를 통한 시스템 모니터링

## 🏗️ 시스템 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Naver News    │    │   ECOS API      │    │   OpenAI API    │
│      API        │    │  (한국은행)      │    │                 │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FinSight Server                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Collectors  │  │ Processors  │  │       Services          │  │
│  │  (수집)      │  │   (가공)     │  │      (비즈니스)          │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                 PostgreSQL Database                             │
└─────────────────────────────────────────────────────────────────┘
                      ▲
                      │
┌─────────────────────▼───────────────────────────────────────────┐
│              Monitoring Stack                                   │
│         Prometheus + Grafana + Node Exporter                    │
└─────────────────────────────────────────────────────────────────┘
```

## 🔄 데이터 파이프라인

### 1. 뉴스 수집 파이프라인 (pipeline.py)

```
1. 키워드 기반 뉴스 수집 (네이버 API)
   ↓
2. 웹 크롤링으로 전문 수집 (newspaper3k)
   ↓
3. LLM 기반 내용 분석 및 카테고리 분류
   ↓
4. 결과 저장 및 상태 업데이트
```

### 2. 경제지표 수집 파이프라인 (ECOS)

```
1. 한국은행 ECOS API 호출
   ↓
2. 경제지표 데이터 수집
   ↓
3. 데이터 정규화 및 저장
   ↓
4. 메타데이터 관리
```

## 📋 주요 구성 요소

### Core Modules

- **collectors.py**: 외부 API를 통한 데이터 수집
- **processors.py**: 데이터 가공 및 AI 분석
- **services.py**: 비즈니스 로직 및 데이터베이스 연동

### API Endpoints

- **GET /**: 서버 상태 확인
- **GET /health**: 헬스체크
- **GET /articles**: 뉴스 기사 조회
- **GET /metrics**: Prometheus 메트릭

### Database Schema

- **articles**: 뉴스 기사 메타데이터
- **article_contents**: 뉴스 본문 내용
- **enriched_articles**: AI 분석 결과
- **statistics**: 경제지표 데이터

## 🛠️ 기술 스택

### Backend
- **FastAPI**: 웹 프레임워크
- **SQLAlchemy**: ORM
- **Alembic**: 데이터베이스 마이그레이션
- **PostgreSQL**: 메인 데이터베이스

### AI/ML
- **OpenAI API**: LLM 분석
- **KSS**: 한국어 문장 분리 (선택적 사용)
- **newspaper3k**: 웹 크롤링

### 모니터링
- **Prometheus**: 메트릭 수집
- **Grafana**: 시각화 대시보드
- **Node Exporter**: 시스템 메트릭

### 데이터 소스
- **네이버 뉴스 API**: 뉴스 수집
- **한국은행 ECOS API**: 경제지표 수집

## 🚀 설치 및 실행

### 1. 환경 설정

```bash
# 프로젝트 클론
cd fin_sight_server

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 의존성 설치
pip install -e .
```

### 2. 환경 변수 설정

`.env` 파일을 생성하고 다음 값들을 설정하세요:

```env
# Database
DATABASE_URL=postgresql://username:password@localhost/finsight

# External APIs
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret
OPENAI_API_KEY=your_openai_api_key
ECOS_API_KEY=your_ecos_api_key

# Application
DEBUG=True
LOG_LEVEL=INFO
```

### 3. 데이터베이스 설정

```bash
# 데이터베이스 마이그레이션
alembic upgrade head
```

### 4. 서버 실행

```bash
# FastAPI 서버 시작
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 데이터 파이프라인 실행
python pipeline.py
```

### 5. 모니터링 (선택사항)

```bash
# Docker Compose로 모니터링 스택 실행
docker-compose up -d

# Grafana 접속: http://localhost:3000
# Prometheus 접속: http://localhost:9090
```

## 📊 API 사용 예시

### 뉴스 기사 조회
```bash
curl -X GET "http://localhost:8000/articles?limit=10&skip=0"
```

### 헬스체크
```bash
curl -X GET "http://localhost:8000/health"
```

### 시스템 메트릭
```bash
curl -X GET "http://localhost:8000/metrics"
```

## 🗂️ 프로젝트 구조

```
fin_sight_server/
├── app/                    # 메인 애플리케이션
│   ├── api/               # API 엔드포인트
│   ├── core/              # 핵심 비즈니스 로직
│   ├── models/            # 데이터베이스 모델
│   ├── schemas/           # Pydantic 스키마
│   └── database.py        # 데이터베이스 설정
├── ecos/                  # 경제지표 수집 모듈
│   └── data_pipeline/
├── data/                  # 데이터 저장소
├── logs/                  # 로그 설정 및 파일
├── scripts/               # 유틸리티 스크립트
├── alembic/               # 데이터베이스 마이그레이션
├── docker-compose.yml     # 모니터링 스택
├── pipeline.py            # 메인 데이터 파이프라인
└── pyproject.toml         # 프로젝트 설정
```

## 🔧 주요 설정

### 수집 키워드
현재 설정된 금융 관련 키워드:
- 금리, 주식, 부동산, 채권
- 코인, 가상자산, 펀드, ETF
- 경제지표, 환율

### 지원하는 경제지표 (ECOS)
- 기준금리, 환율(USD/KRW)
- CPI(소비자물가지수), PPI(생산자물가지수)
- GDP, 경상수지
- 국고채 수익률(3년, 10년)
- KOSPI 지수

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스를 따릅니다.

## 📞 문의

프로젝트에 대한 문의사항이나 버그 리포트는 GitHub Issues를 통해 남겨주세요.

---

**FinSight Server** - 금융 데이터의 인사이트를 제공하는 지능형 뉴스 분석 시스템
