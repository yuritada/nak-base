"""
MVP版 キューサービス
シンプルなFIFOキュー（task_idのみ）
"""
import redis
from ..config import get_settings

settings = get_settings()

TASK_QUEUE = "tasks"


def get_redis_client():
    """Get Redis client."""
    return redis.from_url(settings.redis_url)


def push_task(task_id: int) -> bool:
    """
    タスクIDをキューに追加
    """
    client = get_redis_client()
    try:
        client.rpush(TASK_QUEUE, str(task_id))
        return True
    except Exception as e:
        print(f"Error pushing task to queue: {e}")
        return False


def pop_task() -> int | None:
    """
    タスクIDをキューから取得（ブロッキング）
    """
    client = get_redis_client()
    try:
        result = client.blpop(TASK_QUEUE, timeout=30)
        if result:
            _, data = result
            return int(data)
        return None
    except Exception as e:
        print(f"Error popping task from queue: {e}")
        return None


def get_queue_length() -> int:
    """Get current queue length."""
    client = get_redis_client()
    return client.llen(TASK_QUEUE)
