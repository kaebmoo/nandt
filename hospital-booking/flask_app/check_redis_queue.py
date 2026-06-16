# flask_app/check_redis_queue.py
# สคริปต์ตรวจ/ล้าง RQ queue ด้วยมือ (manual script — ไม่ใช่ unit test)
# รันเอง: python flask_app/check_redis_queue.py
#
# หมายเหตุ: เดิมไฟล์นี้ชื่อ test_queue.py ทำให้ pytest collect แล้ว "ล้าง queue จริง" ตอน import
# (q.empty() อยู่ระดับ module). ย้ายมาชื่อนอก pattern test_* + ห่อด้วย __main__ guard แล้ว
import os

from dotenv import load_dotenv
from redis import Redis
from rq import Queue


def main():
    load_dotenv()
    redis_conn = Redis(
        host=os.environ.get('REDIS_HOST', 'localhost'),
        port=int(os.environ.get('REDIS_PORT', 6379)),
        db=int(os.environ.get('REDIS_DB', 0)),
    )
    print(f"Redis ping: {redis_conn.ping()}")

    q = Queue('default', connection=redis_conn)
    print(f"Queue length: {len(q)}")

    q.empty()
    print(f"Queue length after empty: {len(q)}")

    failed = q.failed_job_registry
    print(f"Failed jobs: {failed.count}")
    for job_id in failed.get_job_ids():
        failed.remove(job_id)
    print("Failed jobs cleared")

    job = q.enqueue('print', 'Test message')
    print(f"Job ID: {job.id}")
    print(f"Queue length after enqueue: {len(q)}")


if __name__ == "__main__":
    main()
