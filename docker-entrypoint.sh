#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] Starting FinSight container..."

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

if [[ $# -eq 0 ]]; then
  if [[ "${SKIP_DB_MIGRATIONS:-0}" != "1" && -f "alembic.ini" ]]; then
    echo "[entrypoint] Running migrations..."
    if ! alembic upgrade head; then
      echo "[entrypoint] Migration failed"; exit 1
    fi
  else
    echo "[entrypoint] Skipping migrations"
  fi
  echo "[entrypoint] Launching API server (uvicorn)"
  exec uvicorn app.main:app --host 0.0.0.0 --port 8000
else
  echo "[entrypoint] Custom command detected, bypassing server + migrations: $*"
  exec "$@"
fi
