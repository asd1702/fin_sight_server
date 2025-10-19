# 뉴스 파이프라인 가이드

이 문서는 `scripts/news/pipeline.py`를 통해 뉴스(네이버 검색 → 크롤링 → LLM 분석 → Enriched 저장) 파이프라인을 실행하는 방법을 정리합니다.

## 개요
- 검색어 목록을 기준으로 네이버 검색 API 호출
- 기사 원문을 newspaper3k로 크롤링(제목/본문/이미지 추출)
- 본문 길이 기준(예: 200자) 하에서 usable 기사만 저장
- PENDING 기사들에 대해 LLM 분석 실행(카테고리, 배경지식 등) 후 EnrichedArticle로 저장
- LLM이 제안한 관련 지표 id로 시계열 데이터를 조회하여 기사와 함께 저장

## 필요 환경
- `DATABASE_URL`: PostgreSQL 연결
- `OPENAI_API_KEY`: LLM 분석 호출
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`: 네이버 검색 API 사용 시 필요

> 로컬 개발에서는 `.env`를 사용하고, 운영에서는 시크릿 매니저나 `--env-file`로 주입하세요.

## 빠른 실행
```bash
python scripts/news/pipeline.py
```

## 동작 상세
1. 키워드 루프 → 네이버 검색 API 결과 메타 받아오기
2. 기사 원문 URL에 대해 newspaper3k로 크롤링(본문/이미지)
3. 본문이 너무 짧으면(기본 200자) 스킵
4. Article/ArticleContent DB 저장(중복 URL 시 스킵/업데이트는 services 레이어 로직에 따름)
5. PENDING 기사 목록 조회 → 상태를 PROCESSING으로 전환
6. LLM 분석(내용 기반 분석) 실행, 결과 유효성 체크
7. 관련 지표 id 목록으로 시계열 데이터 조회(기사 시점 기준) → 합성 컨텍스트 생성
8. EnrichedArticle 저장 후 기사 상태 업데이트

## 운영/스케줄
- 키워드/디스플레이 수, 최소 본문 길이 등은 트래픽/비용에 맞춰 조정하세요.
- 배치 스케줄링 시 API 쿼터를 고려해 주기/동시성을 제한하는 것을 권장합니다.

## 트러블슈팅
- 네이버/크롤러/LLM API 오류: 로그 기록 후 해당 기사 FAILED 처리
- 예기치 못한 예외: rollback 후 FAILED 처리(다음 기사 계속)

### 설정 팁
- 최소 본문 길이, 키워드 세트, 동시성/배치 크기 등은 `app/core/config.py`에 있는 설정들을 활용해 외부화하는 것을 권장합니다.
- 쿼터/요금 보호를 위해 키워드 수와 display 개수를 운영 환경에 맞게 조정하세요.

## 연계
- API로 노출되는 기사 조회/검색/상세는 `app/api/articles.py` 참고
- EnrichedArticle의 스키마/모델은 `app/models` 및 `app/schemas` 참고

### 흔한 이슈와 대응
| 증상 | 원인 | 대응 |
|------|------|------|
| 기사 본문이 비어 있음 | 일부 도메인 크롤링 차단/구조 변경 | 예외 도메인 블랙리스트 추가 또는 크롤러 보완 |
| LLM 응답 필드 누락 | 프롬프트/모델 응답 변동 | 스키마 검증 강화 및 재시도 로직 추가 고려 |
| Enriched 저장 실패 | 스키마/관계 무결성 | services 저장 로직/모델 제약 확인 후 수정 |

## 예시/확장
- 키워드 목록을 `.yaml`로 외부화하여 운영자가 쉽게 변경
- rate limit(슬립/토큰버킷) 적용
- OpenTelemetry trace와 Prometheus custom metrics 추가
