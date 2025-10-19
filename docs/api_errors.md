# API 오류/상태 코드 가이드

이 문서는 현재 코드 기준으로 각 API 엔드포인트가 어떤 상황에서 어떤 상태 코드와 메시지를 반환하는지 요약합니다. FastAPI의 `HTTPException`을 사용한 오류는 기본적으로 `{ "detail": "메시지" }` 형태로 반환됩니다.

주의: 이 문서는 실제 코드에 근거합니다. 변경 시 본 문서도 함께 갱신하세요.

---
## 공통 규칙
- 성공 응답: 200 OK(본문 포함) 또는 204 No Content(본문 없음)로 반환됩니다.
- 오류 응답: `HTTPException` 사용 시 JSON 본문은 `{ "detail": "..." }` 형식입니다.
- 관리자 인증(articles/admin): 헤더 `X-ADMIN-KEY` 필요.
  - 미구성(ADMIN_API_KEY 없음): 503 Service Unavailable `{detail: "Admin API not configured"}`
  - 불일치: 401 Unauthorized `{detail: "Unauthorized"}`
  - 개발 모드 우회: `UNSAFE_ADMIN_MODE=1/true`면 인증 우회(운영때는 지양바람)

---
## 헬스 체크
GET `/health`
- 200 OK: `{ "status": "ok", "database": "connected" }`
- 200 OK(오류 케이스도 200): `{ "status": "error", "database": "disconnected", "error": "connection_failed" }`

---
## 기사(Articles)
### GET `/api/articles/today`
- 200 OK: 최근 PROCESSED 기사 목록
- 400 Bad Request: 잘못된 파라미터(`skip<0` 또는 `limit∈/∉[1,100]`에서 범위 벗어남)
  - `{ "detail": "잘못된 쿼리 파라미터입니다: skip은 0 이상, limit은 1-100 사이여야 합니다" }`
- 500 Internal Server Error: DB 오류/기타 예외
  - `{ "detail": "데이터베이스 연결 오류가 발생했습니다" }` 또는 `{ "detail": "서버 내부 오류가 발생했습니다" }`

### GET `/api/articles/category/{category}`
- 200 OK: 해당 카테고리 기사 목록
- 400 Bad Request: 빈 카테고리 또는 잘못된 페이징 파라미터
- 404 Not Found: 결과 없음
  - `{ "detail": "'{category}' 카테고리의 기사를 찾을 수 없습니다" }`
- 500 Internal Server Error: DB/기타 오류

### GET `/api/articles/search?q=...`
- 200 OK: 검색 결과 목록
- 400 Bad Request: 빈 q 또는 잘못된 페이징 파라미터
  - `{ "detail": "q 파라미터는 필수이며 빈 값일 수 없습니다" }`
- 500 Internal Server Error: DB/기타 오류

### GET `/api/articles/{article_id}`
- 200 OK: 기사 상세(EnrichedArticle 메타 포함)
- 400 Bad Request: `article_id <= 0`
  - `{ "detail": "기사 ID는 양의 정수여야 합니다" }`
- 404 Not Found: 기사 없음
  - `{ "detail": "ID {id}인 기사를 찾을 수 없습니다" }`
- 422 Unprocessable Entity: 아직 처리(PROCESSED) 전
  - `{ "detail": "ID {id}인 기사가 아직 처리 중입니다" }`
- 500 Internal Server Error: DB/기타 오류

### 관리자(Admin) 엔드포인트 (공통: `X-ADMIN-KEY` 필요)
- DELETE `/api/articles/admin/{article_id}`
  - 204 No Content: 성공 또는 이미 삭제된 경우(멱등)
  - 400 Bad Request: 잘못된 ID
  - 404 Not Found: 기사 없음
  - 401/503: 인증 실패/미구성

- POST `/api/articles/admin/{article_id}/restore`
  - 204 No Content: 성공 또는 이미 삭제되지 않은 경우(멱등)
  - 400/404/401/503: 위와 동일

- DELETE `/api/articles/admin/{article_id}/purge`
  - 204 No Content: 성공(없어도 멱등)
  - 400 Bad Request: 잘못된 ID
  - 409 Conflict: 삭제 락 시간 전 `{ "detail": "락 시간이 지나야 영구 삭제 가능" }`
  - 401/503: 인증 실패/미구성

---
## 뉴스레터(Letters)
### GET `/api/letters/{sector}/{key}`
- 200 OK: 최신 배치 초안(Outline)
- 404 Not Found: 없음 `{ "detail": "해당 (sector,key) 초안이 없습니다" }`

### GET `/api/letters/{sector}/{key}/history`
- 200 OK: 배치 이력 목록(없으면 `[]`)

### POST `/api/letters/{sector}/{key}/{batch_id}/publish`
- 200 OK: 발행 완료 또는 이미 발행된 상태 반환
- 404 Not Found: 대상 초안 없음 `{ "detail": "대상 초안이 없습니다" }`

---
## 파라미터 제약(요약)
- 공통 페이징: `skip >= 0`, `1 <= limit <= 100`
- 기사 상세: `article_id > 0`
- 관리자 기능: `X-ADMIN-KEY` 필요, `UNSAFE_ADMIN_MODE`는 개발용 우회

---
## 비고
- `/health`는 오류 케이스에도 200 OK로 응답(본문 status 필드로 판별). 운영 환경에서 상태 코드를 달리하고 싶다면 엔드포인트 로직 조정을 고려하세요.
- 에러 메시지는 국제화(i18n) 또는 표준 에러 스키마(JSON:API 등)로 추후 통일 가능.
