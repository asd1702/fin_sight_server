#!/usr/bin/env bash
set -euo pipefail

## Entrypoint script
## 역할: 컨테이너 시작 시 DB 가용성 검사, 마이그레이션 실행(옵션), 그리고 uvicorn 실행을 담당합니다.
## 중요:
## - 컨테이너는 non-root 사용자(`appuser`)로 실행됩니다. 빌드 단계에서 소유권을 설정합니다.
## - 로그 디렉터리가 없을 경우 복구 시도만 합니다(권한 문제로 실패해도 무시).

echo "[entrypoint] Starting FinSight container..."

# NOTE: We run as non-root (appuser). Avoid chown loops; rely on build-time ownership.
# If logs dir missing (e.g., was pruned), recreate it (best-effort, ignore failures).
if [ ! -d "/app/logs" ]; then
    mkdir -p /app/logs 2>/dev/null || true
fi

# Build uvicorn runtime flags based on env (production quiet mode support)
APP_LOG_LEVEL=${LOG_LEVEL:-info}
UVICORN_FLAGS="--host 0.0.0.0 --port 8000"

if [[ "${QUIET:-0}" == "1" ]]; then
  # PROD에서 QUIET=1이면 access log 억제 및 로그 레벨 warning
  UVICORN_FLAGS+=" --log-level warning --no-access-log"
else
  # Allow disabling access log separately
  if [[ "${UVICORN_NO_ACCESS_LOG:-0}" == "1" ]]; then
    UVICORN_FLAGS+=" --no-access-log"
  fi
  # Normalize log level to lower-case
  lc_level=$(echo "$APP_LOG_LEVEL" | tr 'A-Z' 'a-z')
  UVICORN_FLAGS+=" --log-level ${lc_level}"
fi

# If running default command (no custom CMD) and DATABASE_URL provided, wait for DB to be reachable.
# 운영(RDS) 환경에서는 DATABASE_URL이 외부 호스트를 가리키도록 설정되어 있고,
# 로컬 개발 환경에서는 docker-compose의 `db` 서비스가 DATABASE_URL을 내부 주소(db:5432)를 가리키게 됩니다.
if [[ $# -eq 0 && -n "${DATABASE_URL:-}" ]]; then
  host_and_port=$(python - <<'PY'
import os, urllib.parse as up
url=os.environ.get('DATABASE_URL','')
if url.startswith('postgres'):
    p=up.urlparse(url)
    print(f"{p.hostname}:{p.port or 5432}")
PY
)
  db_host=${host_and_port%:*}
  db_port=${host_and_port#*:}
  if [[ -n "$db_host" ]]; then
    if [[ "$db_host" == "host.docker.internal" ]]; then
      # Linux 에서 host.docker.internal 미존재 시 대체
      getent hosts host.docker.internal >/dev/null 2>&1 || {
        echo "[entrypoint] host.docker.internal not found; trying gateway fallback";
        db_host=$(ip route show default | awk '/default/ {print $3; exit}')
        echo "[entrypoint] Fallback DB host: $db_host"
      }
    fi
    echo "[entrypoint] Waiting for database $db_host:$db_port ..."
    for i in {1..40}; do
      if nc -z "$db_host" "$db_port" 2>/dev/null; then
        echo "[entrypoint] Database reachable."; break
      fi
      sleep 1
      [[ $i -eq 40 ]] && { echo "[entrypoint] DB wait timeout"; exit 1; }
    done
  fi
fi

# 기본 커맨드(인자 없음)일 때는 마이그레이션(옵션)을 실행하고 서버를 띄웁니다.
if [[ $# -eq 0 ]]; then
  if [[ "${SKIP_DB_MIGRATIONS:-0}" != "1" && -f "alembic.ini" ]]; then
    echo "[entrypoint] Running migrations..."
    if ! alembic upgrade head; then
      echo "[entrypoint] Migration failed"; exit 1
    fi
  else
    echo "[entrypoint] Skipping migrations"
  fi
  echo "[entrypoint] Launching API server (uvicorn) flags: ${UVICORN_FLAGS}" 
  exec uvicorn app.main:app ${UVICORN_FLAGS}
else
  # 인자가 있으면 사용자가 제공한 커맨드를 실행합니다(주로 디버그 또는 마이그레이션 전용)
  echo "[entrypoint] Custom command detected, bypassing server + migrations: $*"
  exec "$@"
fi
