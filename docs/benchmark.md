# DB 인덱스 벤치마크 — 목록 조회 · 한국어 검색

README의 인덱싱 관련 주장을 뒷받침하는 측정 기록입니다. 모든 수치는 `EXPLAIN (ANALYZE, BUFFERS)` 기준이며, 각 케이스를 3회 측정했습니다(아래 표는 중앙값).

## 요약

| 대상 | Before | After | 배수 | 실행계획 변화 |
| --- | ---: | ---: | ---: | --- |
| 목록 조회 (`/today`) | ~11.1 ms | **~0.08 ms** | ~140× | Seq Scan + Sort → **Index Scan** (정렬 제거) |
| 한국어 검색 (`/search`, '삼성') | ~104 ms | **~2.6 ms** | ~40× | Seq Scan → **Bitmap Index Scan** (pg_bigm) |
| (중간 시도) pg_trgm GIN | ~104 ms | ~90 ms · 강제 사용 시 **162 ms** | 개선 없음 | 2글자 한국어 색인 불가로 인덱스 무효 |

## 환경

- PostgreSQL 16 (로컬 Docker), pg_bigm 실험은 pg_bigm 포함 이미지(`pg16-bigm`) 별도 컨테이너
- 데이터: `articles` 합성 데이터 50,000행(목록 조회) / 100,000행(검색)
- 검색어 '삼성' 선택도: 1%(1,000행) 및 0.2%(200행) 두 조건
- 쿼리는 실제 앱 쿼리와 동일 형태 (`status`·`is_deleted` 필터 + `published_at DESC` + `LIMIT 20`)

---

## 실험 1. 목록 조회 — 복합 인덱스

목록 API는 `WHERE status = 'PROCESSED' AND is_deleted = false ORDER BY published_at DESC LIMIT 20` 패턴입니다.

**Before (인덱스 없음, 5만 행):** 전 행을 읽고 정렬 후 상위 20건을 잘라냅니다.

```text
Limit (actual time=..11.8)
  -> Sort (Sort Method: top-N heapsort)
       -> Seq Scan on articles (rows=50000)
Execution Time: 11.832 ms   (3회: 11.8 / 10.9 / 11.1)
```

**After (`(status, is_deleted, published_at DESC)` 복합 인덱스):** 인덱스가 필터와 정렬 순서를 모두 커버해 20건만 읽고 끝납니다.

```text
Limit (actual time=..0.05)
  -> Index Scan using idx_articles_list on articles (rows=20)
Execution Time: 0.050 ms   (3회: 0.050 / 0.082 / 0.247)
```

- 깊은 페이지네이션(`OFFSET 10000`)에서도 2.1~3.0 ms로 유지
- **실제 스키마(10만 행) 검증:** 동일 계획으로 0.051 ms (`list_index_verify`)

---

## 실험 2. 한국어 부분일치 검색

### 2-1. 측정 착시를 먼저 걸러냄

최초 벤치마크에서 pg_trgm GIN 적용 후 검색이 0.08 ms로 나왔지만, 실행계획을 보니 **pg_trgm 인덱스가 아니라 실험 1의 목록 인덱스**를 타고 있었습니다(선택도 1%라 최신순으로 20건을 금방 채움). pg_trgm 효과를 분리하기 위해 목록 인덱스를 드랍하고 재측정했습니다.

### 2-2. pg_trgm은 2글자 한국어에서 무효

목록 인덱스 제거 후(10만 행, 1%):

| 조건 | 실행 시간 (3회) | 계획 |
| --- | --- | --- |
| 인덱스 없음 | 94.8 / 108.0 / 104.2 ms | Seq Scan |
| **pg_trgm GIN 적용** | 79.7 / 90.5 / 105.8 ms | **여전히 Seq Scan** |

플래너가 인덱스를 거부하는 이유를 확인하려고 Seq Scan을 강제로 끄고 재실행한 진단 결과가 결정적이었습니다:

```text
Bitmap Heap Scan on articles (actual .. rows=200)
  Rows Removed by Index Recheck: 99800        ← 인덱스가 사실상 전 행을 매치
  -> Bitmap Index Scan on idx_articles_title_trgm (rows=100000)
Execution Time: 162.171 ms                    ← 인덱스를 쓰면 오히려 더 느림
```

pg_trgm은 3-gram 기반이라 '삼성' 같은 **2글자 한국어 토큰을 색인하지 못하고**, 인덱스 스캔이 전 행을 반환한 뒤 recheck에서 99,800행을 버립니다. 플래너의 Seq Scan 선택이 옳았던 것입니다.

### 2-3. pg_bigm 전환 — ILIKE 함정 하나 더

pg_bigm(2-gram) 컨테이너에서 재실험(10만 행, 1%):

| 조건 | 실행 시간 (3회) | 계획 |
| --- | --- | --- |
| 인덱스 없음 | 103.6 / 108.4 / 110.3 ms | Seq Scan |
| pg_bigm GIN + `ILIKE` | 80.2 / 104.4 / 101.8 ms | **여전히 Seq Scan** |
| **pg_bigm `lower()` 함수 인덱스 + `LIKE`** | **2.40 / 2.86 / 2.85 ms** | **Bitmap Index Scan** |

pg_bigm은 `LIKE`(like_ops)만 지원하고 `ILIKE`는 인덱스를 타지 못합니다. 대소문자 무시가 필요했으므로 쿼리를 `lower(col) LIKE lower(:q)`로 바꾸고 `gin_bigm_ops` 함수 기반 인덱스를 생성해 해결했습니다.

```text
Bitmap Heap Scan on articles (actual time=0.243..2.260 rows=1000)
  -> BitmapOr
       -> Bitmap Index Scan on idx_title_bigm_lower  (rows=1000)
       -> Bitmap Index Scan on idx_desc_bigm_lower   (rows=0)
Execution Time: 2.395 ms
```

정렬·LIMIT이 포함된 실제 앱 쿼리 형태에서도 2.8~3.2 ms로 동일한 계획을 유지했습니다.

### 2-4. 실제 스키마 마이그레이션 검증

합성 벤치와 별도로, 실제 마이그레이션 SQL을 적용한 스키마(10만 행)에서 인덱스 생성과 실행계획을 검증했습니다 (`pgbigm_migration_verify`).

- 적용 후 인덱스: `idx_articles_list`, `idx_articles_title_bigm_lower`, `idx_articles_desc_bigm_lower`
- 순수 검색: 2.63 ms (Bitmap Index Scan) · 앱 검색 쿼리: 1.4~2.7 ms

---

## 결론

1. 목록 조회는 필터+정렬을 모두 커버하는 복합 인덱스로 **~11 ms → ~0.08 ms** (정렬 연산 제거).
2. "인덱스를 걸었다"와 "인덱스를 탄다"는 다르다 — 실행계획으로 확인하지 않았으면 pg_trgm의 착시 수치(0.08 ms)를 성과로 오해했을 것.
3. CJK 2글자 검색은 pg_trgm으로 해결되지 않으며(강제 사용 시 악화), **pg_bigm + `lower()` 함수 인덱스** 조합으로 **~104 ms → ~2.6 ms**.

## 원문 로그

측정 원문은 `docs/benchmarks/raw/`에 있습니다.

| 파일 | 내용 |
| --- | --- |
| `bench_result.txt` | 목록/검색 기본 벤치 (5만 행) + pg_trgm 분리 실험 |
| `search_v2_result.txt` | 검색 재실험 (10만 행, 1%·0.2%) + Seq Scan 강제 진단 |
| `bigm_result.txt` | pg_bigm 컨테이너 실험 (ILIKE → lower() LIKE) |
| `pgbigm_migration_verify.txt` | 실제 마이그레이션 SQL 적용 검증 |
| `list_index_verify.txt` | 실스키마 목록 인덱스 검증 |
