"""
SSEストリーミングルーター
Phase 1.5: sse-starletteによるリアルタイム通知
"""
import asyncio
import json
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from ..services.queue_service import get_redis_client
from ..config import get_settings

router = APIRouter(prefix="/api/stream", tags=["stream"])
settings = get_settings()

# Redis Pub/Sub チャンネル名
NOTIFICATION_CHANNEL = "task_notifications"


async def event_generator(request: Request):
    """
    SSEイベントジェネレーター
    Redis Pub/Subからメッセージを受信してクライアントにストリーミング
    """
    client = get_redis_client()
    pubsub = client.pubsub()
    pubsub.subscribe(NOTIFICATION_CHANNEL)

    try:
        while True:
            # クライアント接続チェック
            if await request.is_disconnected():
                break

            message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if message and message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                yield {
                    "event": "message",
                    "data": data
                }
            else:
                # Keep-alive ping（15秒ごと）
                yield {
                    "event": "ping",
                    "data": ""
                }

            await asyncio.sleep(0.5)

    except asyncio.CancelledError:
        pass
    finally:
        pubsub.unsubscribe(NOTIFICATION_CHANNEL)
        pubsub.close()


@router.get("/notifications")
async def stream_notifications(request: Request):
    """
    SSEによるリアルタイム通知ストリーム

    エンドポイント: GET /api/stream/notifications

    イベントデータ形式:
    {
        "task_id": 1,
        "status": "PARSING",
        "phase": "PDF解析中 (1/3)",
        "error_message": null
    }

    使用例（JavaScript）:
    ```javascript
    const eventSource = new EventSource('/api/stream/notifications');
    eventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('Task update:', data);
    };
    ```
    """
    return EventSourceResponse(
        event_generator(request),
        ping=15,  # 15秒ごとにpingを送信
        ping_message_factory=lambda: {"event": "ping", "data": ""}
    )
