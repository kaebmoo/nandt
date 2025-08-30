# flask_app/app/services/redis_connection.py
from redis import Redis
from rq import Queue
import os

class RedisManager:
    _instance = None
    _redis_conn = None
    _queues = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._redis_conn is None:
            self._redis_conn = Redis(
                host=os.environ.get('REDIS_HOST', 'localhost'),
                port=int(os.environ.get('REDIS_PORT', 6379)),
                db=int(os.environ.get('REDIS_DB', 0))
                # ลบ decode_responses=True ออก
            )
    
    @property
    def connection(self):
        """Get Redis connection"""
        return self._redis_conn
    
    def get_queue(self, name='default'):
        """Get or create queue by name"""
        if name not in self._queues:
            self._queues[name] = Queue(name, connection=self._redis_conn)
        return self._queues[name]
    
    def ping(self):
        """Test Redis connection"""
        try:
            return self._redis_conn.ping()
        except:
            return False

# Singleton instance
redis_manager = RedisManager()