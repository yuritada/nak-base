"""
Phase 1.5 キューサービス
job_type対応版
"""
import json
import redis
from ..config import get_settings

settings = get_settings()

TASK_QUEUE = "tasks"
NOTIFICATION_CHANNEL = "task_notifications"


def get_redis_client():
    """Get Redis client."""
    return redis.from_url(settings.redis_url)


def push_task(task_id: int) -> bool:
    """
    タスクIDをキューに追加（後方互換性のため維持）
    """
    client = get_redis_client()
    try:
        client.rpush(TASK_QUEUE, str(task_id))
        return True
    except Exception as e:
        print(f"Error pushing task to queue: {e}")
        return False


def push_task_with_payload(
    task_id: int,
    job_type: str = "ANALYSIS",
    conference_id: str | None = None,
    parent_paper_id: int | None = None
) -> bool:
    """
    タスクIDとジョブタイプをキューに追加

    Args:
        task_id: タスクID
        job_type: "ANALYSIS" (通常解析) または "REFERENCE_ONLY" (参考論文)
        conference_id: 対象学会ID（Phase 1-3）
        parent_paper_id: 前回論文ID（再提出の場合）

    Returns:
        bool: 成功/失敗
    """
    client = get_redis_client()
    try:
        payload = {
            "task_id": task_id,
            "job_type": job_type
        }
        # Phase 1-3: コンテキスト情報を追加
        if conference_id:
            payload["conference_id"] = conference_id
        if parent_paper_id:
            payload["parent_paper_id"] = parent_paper_id

        client.rpush(TASK_QUEUE, json.dumps(payload))
        return True
    except Exception as e:
        print(f"Error pushing task to queue: {e}")
        return False


def publish_notification(
    task_id: int,
    status: str,
    phase: str | None = None,
    error_message: str | None = None
) -> bool:
    """
    タスク通知をRedis Pub/Subに発行

    Args:
        task_id: タスクID
        status: タスクステータス
        phase: 処理フェーズの説明
        error_message: エラーメッセージ

    Returns:
        bool: 発行成功/失敗
    """
    client = get_redis_client()
    try:
        notification = {
            "task_id": task_id,
            "status": status,
            "phase": phase,
            "error_message": error_message,
        }
        client.publish(NOTIFICATION_CHANNEL, json.dumps(notification))
        return True
    except Exception as e:
        print(f"Error publishing notification: {e}")
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
