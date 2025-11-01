# flask_app/simple_test.py
import os
from dotenv import load_dotenv
load_dotenv()

from redis import Redis
from rq import Queue

# Direct connection test
redis_conn = Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    db=int(os.environ.get('REDIS_DB', 0))
)

print(f"Redis ping: {redis_conn.ping()}")

# Test queue
q = Queue('default', connection=redis_conn)
print(f"Queue length: {len(q)}")

# Clear all jobs
q.empty()
print(f"Queue length after: {len(q)}")

# Clear failed jobs
failed = q.failed_job_registry
print(f"Failed jobs: {failed.count}")
for job_id in failed.get_job_ids():
    failed.remove(job_id)
print("Failed jobs cleared")

# Test enqueue
job = q.enqueue('print', 'Test message')
print(f"Job ID: {job.id}")
print(f"Queue length after: {len(q)}")