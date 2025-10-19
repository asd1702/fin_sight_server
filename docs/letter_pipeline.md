# 레터/섹터 파이프라인 가이드

이 문서는 뉴스레터(섹터/기업) outline 생성 파이프라인의 사용법과 내부 개념을 표준 양식으로 정리합니다.

## 핵심 개념
| 개념 | 설명 | 비고 |
|------|------|------|
| Sector | macro / market / tech / company 등 상위 카테고리 | `sectors.yaml` 정의 또는 동적(company) |
| Key (key_word) | 섹터 내 특정 주제 식별자 (예: `us_economy`, `us_market`, `ai_industry`, `nvidia`) | DB `letters.batches.key_word` |
| Batch | 한 번의 수집 & LLM 실행 단위 (기사 묶음 + outline 1개) | 테이블: `letters.batches` |
| Item | 수집된 개별 기사(메타+본문) | 테이블: `letters.items` |
| Outline | LLM이 생성한 최종 JSON 초안 | 테이블: `letters.outlines` (batch_id 1:1) |

## 실행 스크립트 개요
### 1. `scripts/letter/run_sector.py` (권장)
Config + 동적 처리를 모두 지원하는 통합 파이프라인.

주요 기능:
- `sectors.yaml` 기반 (sector, key) 구성 로드
- 기사 수집 → 크롤링 → LLM → DB 저장
- 기존 outline 있으면 재사용(LLM 재호출 회피)
- `--fresh` 로 새 batch 강제 생성 (재생성)
- company 섹터는 sectors.yaml 없이도 동적 처리

### 2. `scripts/letter/letter_pipeline.py` (Deprecated)
- 과거 company 전용 파이프라인 → 현재는 `run_sector.py --sector company` 로 위임.

## DB 구조(요약)
```
letters.batches   (id, sector, key_word, created_at)
letters.items     (id, batch_id, title, url, content, crawl_status, ...)
letters.outlines  (id, batch_id UNIQUE, outline JSONB, status, outline_version, prompt_key, published_at, created_at)
```

## 빠른 실행
```bash
# 사용 가능한 (sector,key) 목록
python3 scripts/letter/run_sector.py --list

# 특정 섹터 구성 상세
python3 scripts/letter/run_sector.py --show-config macro

# 거시경제(us_economy)
python3 scripts/letter/run_sector.py --sector macro --key us_economy

# 시장(us_market) 기사 목표 18개로 실행
python3 scripts/letter/run_sector.py --sector market --key us_market --size 18

# 동적 company (sectors.yaml 필요 없음)
python3 scripts/letter/run_sector.py --sector company --key 회사이름

# 기존 outline 무시하고 새로 생성
python3 scripts/letter/run_sector.py --sector company --key 회사이름 --fresh
```

실행 성공 시 출력:
```
batch:17
```
이는 DB `letters.outlines` 에 outline 이 저장된 batch id.

## 동작 상세/재생성 전략
| 상황 | 동작 | 설명 |
|------|------|------|
| 동일 (sector,key) 재실행 | 기존 outline 있으면 재사용 | LLM 호출 비용 절감 |
| 강제 새로 생성 | `--fresh` | 새 batch + 새 outline (히스토리 가능) |
| 덮어쓰기(미구현) | (추가 가능) | 기존 row 업데이트 & outline_version 증가 |

## 운영/스케줄
- size/쿼리 조정으로 기사 수급 안정화 권장
- 키/섹터별 정기 배치 운영 시 API 한도 고려

## 실패/재시도 정책(현재 구현 기준)
- 수집 단계(NewsData API + 크롤링)
  - NewsData API: 422(UnsupportedParameter) 응답 시 OR 쿼리를 단일 키워드로 분할하여 순차 재시도합니다. 네트워크 오류/타임아웃 시 빈 결과로 처리하여 다음 단계로 넘어가며, 다음 배치 실행에서 다시 조회됩니다.
  - 본문 크롤링(newspaper3k): 제목/본문이 없거나 본문이 200자 미만이면 해당 기사는 건너뜁니다(저장되지 않음). 예외 발생 시도 해당 URL은 스킵됩니다.
- LLM 단일 기사 분석
  - OpenAI 호출 결과가 JSON 파싱 실패이거나 API 오류인 경우 None으로 처리되어 해당 기사의 분석은 생략됩니다. 이후 실행에서 동일 기사가 다시 후보가 되면 재시도될 수 있습니다.
- 번들 아웃라인 생성(run_sector)
  - 최대 3회 적응형 시도(기사 수/입력 예산 점진 감소)를 수행합니다. 각 시도에서 JSON 파싱 실패나 API 오류가 나면 다음 시도로 진행하고, 모든 시도 실패 시 None을 반환합니다(이 배치에서 아웃라인 생성 실패로 간주).

### API 호출/크롤링 타임아웃·재시도 설정
- NewsData API: 요청 타임아웃 10초. 422 시 단일 키워드 재시도, 그 외 네트워크 오류/타임아웃은 추가 재시도 없음.
- newspaper3k: 요청 타임아웃 10초. 실패 시 해당 URL 스킵.
- OpenAI Chat Completions(단일 기사 분석): LETTER_LLM_TIMEOUT_SECS(기본 60초), LETTER_LLM_CLIENT_RETRIES(기본 3회)를 사용.
- OpenAI 번들 아웃라인: 내부적으로 최대 3회(기사 수/예산을 줄이며) 시도. 각 시도는 모델 max_tokens 한도를 고려.

## company 동적 처리 규칙
- sector='company', key=<원문 소문자+공백→_> slug
- prompt_key='company' 로 공통 프롬프트 사용
- size 지정 없으면 12 기본

## 연계(API)
| Endpoint | 기능 |
|----------|------|
| `GET /api/letters/{sector}/{key}` | 최신 outline 반환 |
| `GET /api/letters/{sector}/{key}/history` | batch 히스토리 목록 |
| `POST /api/letters/{sector}/{key}/{batch_id}/publish` | status='delivered' 설정 |

## 트러블슈팅
| 문제 | 원인 | 대응 |
|------|------|------|
| 기사 부족 | 수집 후 usable < LETTER_MIN_ARTICLES | 쿼리/size 조정 or fresh 실행 |
| UniqueViolation(batch_id) | 재생성 시 기존 outline 존재 | `--fresh` 사용 |
| API 422 (News API) | 쿼리 파라미터 제한 | OR 분할 재시도 로직 내장 |

## 환경 변수(주요)
| 이름 | 역할 | 예시 |
|------|------|------|
| OPENAI_API_KEY | LLM 호출 키 | sk-... |
| DATABASE_URL | PostgreSQL 연결 | postgres://... |
| LETTER_MIN_ARTICLES | LLM 최소 기사 수 | 5 |
| LETTER_LLM_MODEL | OpenAI 모델명 | gpt-4o-mini |
| LETTER_LLM_TIMEOUT_SECS | 단일 기사 분석 LLM 타임아웃(초) | 60.0 |
| LETTER_LLM_CLIENT_RETRIES | 단일 기사 분석 LLM 재시도 횟수 | 3 |
| LETTER_LLM_MAX_ARTICLES | 번들 아웃라인 생성 시 최대 기사 수 | 8 |
| LETTER_LLM_INPUT_BUDGET | 번들 입력 토큰 예산(히ュー리스틱) | 22000 |
| LETTER_LLM_MAX_TOKENS | 번들 응답 토큰 상한 | 1500 |

## 예시(sectors.yaml 발췌)
```yaml
macro:
  us_economy:
    queries: [gdp, inflation, fed policy]
    prompt_key: us_economy
    size: 14
market:
  us_market:
    queries: [s&p 500, market breadth, sector rotation]
    prompt_key: us_market
tech:
  ai_industry:
    queries: [AI demand, datacenter capex]
    prompt_key: tech_industry
```

## 커스텀 팁
- prompt 수정: `app/prompts/prompts.yaml`
- 프롬프트 키 fallback: `get_prompt(topic, kind, fallback_topic='company')`
- 크롤링 블랙리스트/예외 처리: `collectors.py` 확장
- 성능 측정: `@monitor_performance` 데코레이터 로그 확인

## 향후 개선
- regenerate (덮어쓰기) 모드 + outline_version 증가
- outline schema version 필드 활용(test harness)
- token usage 추적(meta) 재도입 (옵션)
- 뉴스 소스 다변화 (RSS, SEC filings 등)

---
문의/수정이 필요하면 이 문서 갱신 후 PR 남기세요.