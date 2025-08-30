# /Users/seal/Documents/GitHub/nandt/hospital-booking/worker.py
import os
import sys
from dotenv import load_dotenv

# Load environment variables from .env file
# This must be done before importing any app modules that need them.
load_dotenv()

# Add the flask_app directory to Python's path
# This allows the worker to find the task functions like `send_otp_sms`
project_root = os.path.dirname(os.path.abspath(__file__))
flask_app_path = os.path.join(project_root, 'flask_app')
sys.path.insert(0, flask_app_path)

from app.services.redis_connection import redis_manager
from rq import Worker, Queue

if __name__ == '__main__':
    # The list of queues to listen on
    listen = ['default']

    # Get the Redis connection from our centralized manager
    redis_conn = redis_manager.connection

    # Create a list of Queue objects, passing the connection to each
    queues = [Queue(name, connection=redis_conn) for name in listen]

    # Create the worker, passing the list of queues and the connection
    worker = Worker(queues, connection=redis_conn)
    print(f"Starting RQ worker for queues: {', '.join(listen)}")
    worker.work(with_scheduler=True) # Use with_scheduler=True to run scheduled jobs if any