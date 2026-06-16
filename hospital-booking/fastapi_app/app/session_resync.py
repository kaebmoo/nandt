"""Best-effort trigger: re-generate queue `sessions` เมื่อ availability/date_override เปลี่ยน (1B.3)

สถาปัตยกรรม (best practice — ไม่เรียกข้าม process แบบ synchronous):
  FastAPI save (persist สำเร็จ) ──enqueue──▶ Redis/RQ ──▶ worker ──▶ session_service.resync_template()

- decouple ผ่าน RQ queue ที่มีอยู่แล้ว (worker.py) — save ยังเร็ว, ล้มแล้ว retry ได้, idempotent
- **ไม่ import flask_app** (กัน cross-import): enqueue ด้วย dotted-path string; worker (ที่ใส่
  flask_app/ ลง sys.path) เป็นคน resolve เอง → 'app.services.session_service.resync_template_sessions_job'
- best-effort: ถ้า enqueue ล้มเหลว (Redis ล่ม ฯลฯ) แค่ log ไม่ทำให้การ save availability ล้มเหลว
  (daily Celery sync เป็น safety net อยู่แล้ว)
"""

import logging
import os

logger = logging.getLogger(__name__)

# dotted-path ตาม namespace ของ worker (worker.py: sys.path มี flask_app/ → 'app' = flask_app/app)
_TEMPLATE_JOB = "app.services.session_service.resync_template_sessions_job"
_TENANT_JOB = "app.services.session_service.resync_tenant_sessions_job"
# NB: ลบ template ทำ cleanup future sessions แบบ synchronous+atomic ใน availability.py
# (ไม่ผ่าน RQ — กัน session ค้างถ้า worker/Redis ล่ม) จึงไม่มี cleanup job ที่นี่


def _enqueue(job_path, *args):
    """enqueue งานเข้า RQ (best-effort — ห้าม raise; daily Celery sync เป็น safety net)"""
    try:
        from redis import Redis
        from rq import Queue

        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        queue = Queue("default", connection=Redis.from_url(redis_url))
        queue.enqueue(job_path, *args, job_timeout="5m")
        logger.info("enqueued %s args=%s", job_path, args)
    except Exception:
        logger.exception("enqueue %s ล้มเหลว args=%s — ข้าม", job_path, args)


def trigger_session_resync(schema_name: str, template_id) -> None:
    """enqueue re-sync session ของ template เดียว (best-effort)"""
    if not schema_name or template_id is None:
        return
    _enqueue(_TEMPLATE_JOB, schema_name, int(template_id))


def trigger_tenant_session_resync(schema_name: str) -> None:
    """enqueue re-sync ทุก service_point ของ tenant — ใช้กับ global date_override (best-effort)"""
    if not schema_name:
        return
    _enqueue(_TENANT_JOB, schema_name)
