# 데이터 파이프라인 & 스크립트 운영 가이드

이 문서는 ECOS(한국은행) 및 기타 경제지표 증분 수집 파이프라인을 장기적으로 안정/확장 가능하게 운영하기 위한 표준 가이드입니다. 스크립트 역할, 실행 순서, 문제 대응 방법을 정리합니다.

---
## 개요/전체 구성

| 레이어 | 구성 요소 | 설명 | 실행 주기 |
|--------|-----------|------|-----------|
| 메타 관리 | `catalog_core15.json` + `scripts/ecos/ingest_catalog.py` | 지표(Indicator) 메타데이터 정의 및 DB 반영 | 필요 시 (새 지표 추가/수정) |
| 상태 추적 | `statistics.indicator_state` | 각 지표 마지막 수집 날짜 / 누적 행수 | ingestion 시 자동 갱신 |
| 증분 수집 | `scripts/ecos/ingest_ecos_incremental.py` | ECOS API 호출하여 신규/최근 구간만 upsert | 배치 (예: 1일 1회) |
| 시드/백업 | `scripts/ecos/export_observations_core.py` | DB 관측치 → JSONL 재생성 (백업/재배포) | 필요 시 (주간/월간) |
| 관측치 저장 | `statistics.observations` | 시계열 값 (indicator_id, date, value) | 지속 |
| 실행 이력 | `statistics.ingestion_runs` | (MVP) 실행별 통계(삽입/스킵/에러) | ingestion 시 기록 |

---
## 핵심 테이블

### 1. `statistics.indicators`
- 지표 메타데이터 (이름, 주기, 단위, ECOS stat_code + item_code* 등).
- 관리 소스: `data/catalog_core15.json` -> `ingest_catalog.py` 로 반영.

### 2. `statistics.observations`
- 복합 PK: (indicator_id, date)
- 값 충돌 시 upsert → value 업데이트 (현재 변경 이력은 별도 저장 안 함).

### 3. `statistics.indicator_state`
| 필드 | 의미 |
|------|------|
| indicator_id | 지표 식별자 |
| last_loaded_date | 마지막으로 load된 날짜 (주기별 anchoring: 월지표는 그 달 1일 등) |
| total_rows | 누적 관측치 행 수(단순 합계) |

### 4. `statistics.ingestion_runs`
- 특정 실행(run)의 총 삽입/스킵/에러 수.
- 향후 per-indicator 상세(run_details) 확장 여지.

---
## 스크립트 상세

### 1) [`scripts/ecos/ingest_catalog.py`](../scripts/ecos/ingest_catalog.py)
**역할:** 카탈로그 JSON을 읽어 indicators 테이블에 upsert. (옵션) indicator_state 초기화.

**주요 옵션:**
- `--file <path>`: 기본 `data/catalog_core15.json`
- `--bootstrap-state`: state 없는 지표에 (last_loaded_date=NULL,total_rows=0) 생성
- `--force-state`: 기존 state 삭제 후 재생성(위험: 이후 ingestion이 전체 재수집)

**빠른 실행:**
```bash
python scripts/ecos/ingest_catalog.py --bootstrap-state
python scripts/ecos/ingest_catalog.py --file data/catalog_new.json --bootstrap-state --force-state
```

**언제 실행?**
1. 새 지표 추가 / 주기(frequency) 수정 / stat_code 변경
2. 신규 환경(스테이징/프로덕션) 런칭 시 초기 세팅
3. 잘못된 state를 강제로 리셋 후 full 재수집하고 싶을 때(`--force-state`)

**주의:**
- `--force-state` 실행 후 즉시 incremental 스크립트 돌리면 2000년~현재까지 full fetch 발생.
- catalog JSON의 frequency가 잘못되면 (예: `.d` 지표인데 M) 현재 구현은 indicator_id suffix로 보정하지만, 향후 명시 주기와 충돌 시 경고 로직 추가 권장.

---
### 2) [`scripts/ecos/ingest_ecos_incremental.py`](../scripts/ecos/ingest_ecos_incremental.py)
**역할:** ECOS API에서 지표별 신규/최근 데이터만 수집(upsert) + state 갱신.

**핵심 로직:**
1. 각 지표의 state(last_loaded_date) 조회
2. 기본 시작일 = (last_loaded_date + 1) 또는 초기값(2000-01-01)
3. `--recheck-days N` 주어지면 최근 N일(또는 N*주기) 구간으로 되감기(rewind) → 최근 값 재검증
4. ECOS 호출 (frequency 추론: indicator_id suffix 우선)
5. 응답 파싱 → 검증 → upsert → state 업데이트

**주요 옵션 (현재 구현):**
- `--recheck-days 7` : 최근 7일 다시 긁어서 혹시 늦게 갱신된 값 보완

**특징:**
- idempotent: 같은 날 여러 번 실행해도 중복 insert 대신 upsert
- 새 달/새 일 데이터만 자연스럽게 추가
- 빈 stat_code 지표는 스킵 (경고 로그)

**빠른 실행:**
```bash
python scripts/ecos/ingest_ecos_incremental.py --recheck-days 7
```

**운영/스케줄(cron) 예:**
```cron
0 3 * * * /venv/bin/python /app/scripts/ecos/ingest_ecos_incremental.py --recheck-days 7 >> /var/log/ingest.log 2>&1
```

**문제 대응:**
| 증상 | 점검 | 대응 |
|------|------|------|
| fetched=0 계속 | URL 구성/ stat_code / item_code 잘못 | catalog 수정 후 re-run |
| 일부 지표 폭증 | frequency mismatch | catalog frequency 보정 or suffix 규칙 확인 |
| state 미갱신 | inserted=0 & bootstrap 필요 | 기존 관측치 있는지 확인 후 수동 state 삽입 |

---
### 3) [`scripts/ecos/export_observations_core.py`](../scripts/ecos/export_observations_core.py)
**역할:** DB 관측치 → JSONL(`observations_core15.jsonl`) 재생성 (백업/재배포/비교).

**옵션:**
- `--only a b c` : 특정 indicator_id만
- `--all` : 카탈로그 무시, 전부 export

**빠른 실행:**
```bash
# 코어 세트 백업
python scripts/ecos/export_observations_core.py --only kr.cpi.headline.m kr.ppi.m kr.base.rate.d fx.usdkrw.m kr.current.account.m kr.kospi.d

# 전체
python scripts/ecos/export_observations_core.py --all
```

**사용 시나리오:**
- 월간 스냅샷 백업 → git 버전 관리
- FE/DS 팀에 최신 데이터 전달
- 다른 환경으로 seed 재생성

**주의:**
- 대량(일자료) 포함 시 파일 커질 수 있음 → gzip 권장
- 현재 변경 이력 없이 덮어쓰기 → 필요시 manifest(hash) 추가 고려

---
## 빈번한 운영 플로우 예시

### 신규 지표 추가
1. `catalog_core15.json` 수정 (새 객체 append)
2. `python3 scripts/ecos/ingest_catalog.py --bootstrap-state`
3. 다음 배치 때 자동 수집 or 즉시 `ingest_ecos_incremental.py` 실행

### 잘못된 stat_code 수정
1. catalog 수정
2. `ingest_catalog.py` 실행 (state는 건드리지 않음)
3. 필요 시 해당 지표 state.last_loaded_date 과거로 수동 조정 → 재수집 유도

### 전체 리셋(드물게)
1. (선택) observations 테이블 백업/export
2. `python3 scripts/ecos/ingest_catalog.py --bootstrap-state --force-state`
3. `ingest_ecos_incremental.py` 실행 → full fetch

### 월간 백업
```bash
python scripts/ecos/export_observations_core.py --only ...코어셋...
# 결과 파일 git add / 또는 gzip
```

---
## 환경 변수(주요)
| 변수 | 용도 | 비고 |
|------|------|------|
| `ECOS_API_KEY` | ECOS 인증키 | .env 또는 환경 주입 |
| `ECOS_PAGE_SIZE` | 페이지 사이즈 (기본 1000) | 큰 값으로 과다 요청 피하기 |

---
## frequency 처리 규칙
- catalog 주기와 indicator_id suffix 충돌 시 suffix 우선 (`.d` → D, `.m` → M 등)
- 일/월/분기/연도 날짜 토큰 변환:
  - D: YYYYMMDD
  - M: YYYYMM
  - Q: YYYYQn (TIME "2024Q1")
  - A/Y: YYYY

---
## 트러블슈팅
| 상황 | 로그 힌트 | 조치 |
|------|-----------|------|
| 모든 지표 fetched=0 | Debug 로그 URL 확인, 응답 RESULT code | stat_code/ item_code 재검증, suffix 주기 확인 |
| 특정 지표만 0 | ECOS 포털에서 직접 REST 테스트 | catalog 해당 행 교정 |
| state 레코드 없음 | bootstrap 미실행 | `ingest_catalog.py --bootstrap-state` 또는 관측치로부터 수동 생성 |
| value 정정 필요 | 현재 upsert value overwrite | 추후 변경 이력 테이블 설계 고려 |

### 실패/재시도 정책(현재 구현 기준)
- API 호출 재시도: EcosApiClient는 각 페이지 요청에 대해 timeout=15초, 최대 3회 재시도(backoff 포함)를 수행합니다. 응답이 200이 아니거나 JSON 파싱 실패 시 재시도하며, 연속 실패 시 마지막 오류와 함께 예외를 발생시킵니다.
- 페이지네이션: 한 페이지에 page_size(기본 1000) 미만이 반환되면 마지막 페이지로 간주하고 다음 페이지 요청을 중단합니다.
- indicator 단위 오류 처리: orchestrator는 지표별 try/except로 보호되어 있어, 특정 지표에서 예외가 발생해도 다른 지표 처리는 계속됩니다. 실패한 지표는 로그에 남고, 전체 run의 status는 삽입/오류 수에 따라 SUCCESS/PARTIAL/FAILED 중 하나로 설정됩니다.
- 트랜잭션/커밋: CLI는 전체 실행이 끝난 뒤 한 번 commit합니다. 중간에 예외가 발생하면 rollback 후 비정상 종료합니다. 개별 지표 처리 중 오류는 카운트만 증가되며 나머지 지표는 처리됩니다.

---
## 향후 개선
1. Upsert 결과: inserted vs updated 분리 (RETURNING + 시스템 컬럼)
2. 관측치 변경 히스토리 테이블(`observations_audit`)
3. export 시 `--since`, `--gzip`, manifest(JSON) 추가
4. fetch 실패(RESULT 코드) 별 재시도/슬랙 알림
5. Prometheus metrics (rows_fetched, rows_inserted, duration_seconds)
6. OpenTelemetry trace (indicator별 span)

---
## 빠른 체크리스트(운영자가 문제 있을 때)
1. API Key 유효? (`echo $ECOS_API_KEY`)
2. catalog 행 stat_code / item_code* 정확? (ECOS 포털 문서 대비)
3. indicator_state.last_loaded_date 정상 증가?
4. 최근 run에서 fetched > 0 / inserted > 0 ?
5. 동일 날 여러 번 실행 시 inserted=0 (또는 매우 적은 수)인지 → idempotent 확인.

---
## FAQ
**Q. catalog 주기(M)인데 `.d` suffix면?** → 내부에서 `.d` 우선 적용, catalog 수정 권장.
**Q. 일부 과거 데이터 누락 발견?** → 해당 지표 state.last_loaded_date를 누락 이전 날짜로 낮춰 UPDATE 후 재실행.
**Q. JSONL seed 계속 필요?** → 운영 자체엔 필수 아님 (DB가 소스), 백업/전달 용도로만 유지.

---
## 예시(SQL)
최근 3개월 CPI 값 확인:
```sql
SELECT date, value
FROM statistics.observations
WHERE indicator_id='kr.cpi.headline.m'
ORDER BY date DESC
LIMIT 3;
```
지표별 마지막 로드 상태:
```sql
SELECT indicator_id, last_loaded_date, total_rows
FROM statistics.indicator_state
ORDER BY indicator_id;
```
특정 지표 state 리셋:
```sql
UPDATE statistics.indicator_state
SET last_loaded_date='2024-12-31', total_rows= (SELECT COUNT(*) FROM statistics.observations WHERE indicator_id='kr.cpi.headline.m')
WHERE indicator_id='kr.cpi.headline.m';
```

---
## 결론
이 문서는: "카탈로그 반영 → 증분 실행 → 백업"의 세 축과 각 스크립트의 안전한 사용법을 표준화합니다. 운영 중 새로운 요구(변경 추적, 알림, 메트릭)가 생기면 상단 로드맵대로 확장하세요.

