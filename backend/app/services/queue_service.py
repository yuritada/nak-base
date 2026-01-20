import redis
import json
from ..config import get_settings

settings = get_settings()

INFERENCE_QUEUE = "inference_tasks"


def get_redis_client():
    """Get Redis client."""
    return redis.from_url(settings.redis_url)


def push_inference_task(task_data: dict) -> bool:
    """
    Push inference task to Redis queue.
    task_data should contain: task_id, version_id, file_id, conference_rule_id
    """
    client = get_redis_client()
    try:
        client.rpush(INFERENCE_QUEUE, json.dumps(task_data))
        return True
    except Exception as e:
        print(f"Error pushing task to queue: {e}")
        return False


def pop_inference_task() -> dict | None:
    """Pop inference task from Redis queue (blocking)."""
    client = get_redis_client()
    try:
        result = client.blpop(INFERENCE_QUEUE, timeout=30)
        if result:
            _, data = result
            return json.loads(data)
        return None
    except Exception as e:
        print(f"Error popping task from queue: {e}")
        return None


def get_queue_length() -> int:
    """Get current queue length."""
    client = get_redis_client()
    return client.llen(INFERENCE_QUEUE)
