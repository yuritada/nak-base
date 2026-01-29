"""
SSE通知ルーター
Phase 1.5: リアルタイム通知
"""
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from ..services.queue_service import get_redis_client
from ..config import get_settings

router = APIRouter(tags=["notifications"])
settings = get_settings()

# Redis Pub/Sub チャンネル名
NOTIFICATION_CHANNEL = "task_notifications"


async def event_generator():
    """
    SSEイベントジェネレーター
    Redis Pub/Subからメッセージを受信してクライアントにストリーミング
    """
    client = get_redis_client()
    pubsub = client.pubsub()
    pubsub.subscribe(NOTIFICATION_CHANNEL)

    try:
        while True:
            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                yield f"data: {data}\n\n"
            else:
                # ハートビート（接続維持用）
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
    finally:
        pubsub.unsubscribe(NOTIFICATION_CHANNEL)
        pubsub.close()


@router.get("/api/stream/notifications")
async def stream_notifications():
    """
    SSEによるリアルタイム通知ストリーム

    イベントデータ形式:
    {
        "task_id": 1,
        "status": "PARSING",
        "phase": "PDF解析中 (1/3)",
        "error_message": null
    }
    """
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def publish_task_notification(
    task_id: int,
    status: str,
    phase: str | None = None,
    error_message: str | None = None
) -> bool:
    """
    タスク通知をRedis Pub/Subに発行（Workerから呼び出す）

    Args:
        task_id: タスクID
        status: タスクステータス（PENDING, PARSING, RAG, LLM, COMPLETED, ERROR）
        phase: 処理フェーズの説明（オプション）
        error_message: エラーメッセージ（オプション）

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
