#!/usr/bin/env bash
#
# start_all.sh - start ทุก service ของระบบ hospital-booking ในคำสั่งเดียว
#
# Usage:
#   ./start_all.sh              # FastAPI + Flask + Admin + RQ worker
#   ./start_all.sh --celery     # เพิ่ม Celery worker + beat (holiday sync)
#   ./start_all.sh --no-admin   # ไม่ start Super Admin panel
#
# กด Ctrl+C เพื่อหยุดทุก service พร้อมกัน
# Log ของแต่ละ service อยู่ที่ logs/<service>.log

set -u
set -m  # job control: แต่ละ service ได้ process group ของตัวเอง จะได้ kill ทั้งกลุ่มตอนปิด

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

WITH_CELERY=false
WITH_ADMIN=true
for arg in "$@"; do
    case "$arg" in
        --celery)   WITH_CELERY=true ;;
        --no-admin) WITH_ADMIN=false ;;
        *) echo "unknown option: $arg"; exit 1 ;;
    esac
done

# ---------- หา Python ที่มี dependency ครบ ----------
find_python() {
    local candidates=()
    [ -n "${PYTHON:-}" ] && candidates+=("$PYTHON")
    [ -n "${VIRTUAL_ENV:-}" ] && candidates+=("$VIRTUAL_ENV/bin/python")
    candidates+=(
        "$ROOT_DIR/venv/bin/python"
        "$ROOT_DIR/.venv/bin/python"
        "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10"
        "python3"
    )
    for py in "${candidates[@]}"; do
        if command -v "$py" >/dev/null 2>&1 && "$py" -c "import flask, fastapi, rq, sqlalchemy" >/dev/null 2>&1; then
            command -v "$py"
            return 0
        fi
    done
    return 1
}

PY="$(find_python)" || {
    echo "❌ ไม่พบ Python ที่ติดตั้ง dependency ครบ (flask, fastapi, rq, sqlalchemy)"
    echo "   ติดตั้งด้วย: pip install -r requirements.txt"
    echo "   หรือระบุเอง: PYTHON=/path/to/python ./start_all.sh"
    exit 1
}
echo "🐍 Python: $PY"

# ---------- โหลด .env ----------
# ใช้ python-dotenv parse (ตัวเดียวกับที่แอปใช้) แทน source ตรงๆ
# เพราะ .env อาจมีรูปแบบอย่าง "KEY = value" ที่ bash source ไม่ได้
if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "❌ ไม่พบไฟล์ .env ที่ $ROOT_DIR"
    exit 1
fi
eval "$("$PY" - <<EOF
from dotenv import dotenv_values
import shlex
for k, v in dotenv_values("$ROOT_DIR/.env").items():
    if v is not None:
        print(f"export {k}={shlex.quote(v)}")
EOF
)"

# ให้ทุก service import shared_db ได้ ไม่ว่า working directory จะอยู่ที่ไหน
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

# ---------- ตรวจ PostgreSQL ----------
if ! "$PY" - <<'EOF' >/dev/null 2>&1
import os, sqlalchemy
engine = sqlalchemy.create_engine(os.environ["DATABASE_URL"], connect_args={"connect_timeout": 3})
with engine.connect():
    pass
EOF
then
    echo "❌ ต่อ PostgreSQL ไม่ได้ (DATABASE_URL=${DATABASE_URL:-ไม่ได้ตั้งค่า})"
    echo "   ตรวจว่า PostgreSQL ทำงานอยู่: brew services start postgresql@16 (หรือ version ที่ใช้)"
    exit 1
fi
echo "✅ PostgreSQL พร้อม"

# ---------- ตรวจ / start Redis ----------
if ! redis-cli ping >/dev/null 2>&1; then
    echo "⏳ Redis ยังไม่ทำงาน กำลังพยายาม start..."
    if command -v brew >/dev/null 2>&1 && brew services start redis >/dev/null 2>&1; then
        sleep 2
    elif command -v redis-server >/dev/null 2>&1; then
        redis-server --daemonize yes >/dev/null 2>&1
        sleep 1
    fi
    if ! redis-cli ping >/dev/null 2>&1; then
        echo "❌ start Redis ไม่สำเร็จ — start เองด้วย: redis-server"
        exit 1
    fi
fi
echo "✅ Redis พร้อม"

# ---------- ตรวจ port ว่าง ----------
check_port_free() {
    local port="$1" name="$2"
    local pids
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        echo "❌ port $port ($name) ถูกใช้อยู่โดย PID: $pids"
        echo "   ปิดก่อนด้วย: kill $pids"
        exit 1
    fi
}
check_port_free 8000 "FastAPI"
check_port_free 5001 "Flask"
$WITH_ADMIN && check_port_free "${ADMIN_PORT:-5002}" "Admin"

# ---------- เริ่ม services ----------
PIDS=()
NAMES=()

start_service() {
    local name="$1" workdir="$2"; shift 2
    ( cd "$workdir" && exec "$@" ) >"$LOG_DIR/$name.log" 2>&1 &
    local pid=$!
    PIDS+=("$pid")
    NAMES+=("$name")
    echo "▶️  $name (pid $pid) → logs/$name.log"
}

wait_for_port() {
    local port="$1" name="$2" tries=30
    while ! curl -s -o /dev/null "http://127.0.0.1:$port/"; do
        tries=$((tries - 1))
        if [ "$tries" -le 0 ]; then
            echo "⚠️  $name ยังไม่ตอบที่ port $port — ดู logs/$name.log"
            return 1
        fi
        sleep 1
    done
    echo "✅ $name ตอบแล้วที่ port $port"
}

cleanup() {
    trap - INT TERM EXIT   # กันไม่ให้ cleanup ถูกเรียกซ้ำ
    echo ""
    echo "🛑 กำลังหยุดทุก service..."
    if [ "${#PIDS[@]}" -gt 0 ]; then
        for i in "${!PIDS[@]}"; do
            # kill ทั้ง process group (ครอบคลุม reloader ของ uvicorn/werkzeug)
            kill -TERM -- -"${PIDS[$i]}" 2>/dev/null || kill -TERM "${PIDS[$i]}" 2>/dev/null
        done
    fi
    wait 2>/dev/null
    echo "👋 หยุดครบทุกตัวแล้ว"
    exit 0
}
trap cleanup INT TERM EXIT

# ลำดับ: FastAPI ก่อน (Flask เรียกใช้) → Flask → Admin → workers
start_service "fastapi" "$ROOT_DIR/fastapi_app" "$PY" -m uvicorn app.main:app --port 8000 --reload
wait_for_port 8000 "fastapi"

start_service "flask" "$ROOT_DIR/flask_app" "$PY" run.py
wait_for_port 5001 "flask"

if $WITH_ADMIN; then
    start_service "admin" "$ROOT_DIR" "$PY" run_admin.py
    wait_for_port "${ADMIN_PORT:-5002}" "admin"
fi

start_service "rq-worker" "$ROOT_DIR" "$PY" worker.py

if $WITH_CELERY; then
    start_service "celery-worker" "$ROOT_DIR" "$PY" -m celery -A flask_app.celery_worker worker --loglevel=info
    start_service "celery-beat" "$ROOT_DIR" "$PY" -m celery -A flask_app.celery_worker beat --loglevel=info
fi

echo ""
echo "=============================================="
echo "🏥 ระบบพร้อมใช้งานแล้ว"
echo "   Flask (หน้าเว็บหลัก):  http://localhost:5001/?subdomain=<ชื่อโรงพยาบาล>"
echo "   FastAPI (API docs):    http://localhost:8000/docs"
$WITH_ADMIN && echo "   Super Admin:           http://localhost:${ADMIN_PORT:-5002}"
echo "   หน้า booking สาธารณะ:   http://localhost:5001/book/?subdomain=<ชื่อโรงพยาบาล>"
echo ""
echo "   กด Ctrl+C เพื่อหยุดทุก service"
echo "=============================================="

# รอจนกว่าจะถูกสั่งหยุด — ถ้า service ใดตายจะแจ้งเตือน
while true; do
    if [ "${#PIDS[@]}" -gt 0 ]; then
        for i in "${!PIDS[@]}"; do
            if ! kill -0 "${PIDS[$i]}" 2>/dev/null; then
                echo "⚠️  ${NAMES[$i]} หยุดทำงานเอง — ดู logs/${NAMES[$i]}.log"
                unset 'PIDS[i]' 'NAMES[i]'
            fi
        done
    fi
    sleep 5
done
