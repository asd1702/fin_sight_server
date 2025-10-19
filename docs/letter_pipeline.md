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