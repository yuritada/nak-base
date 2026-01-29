"""
SSEストリーミングルーター
Phase 1.5: sse-starletteによるリアルタイム通知 (Async Redis版)
"""
import asyncio
import json
from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse
from redis import asyncio as aioredis  # 非同期ライブラリを使用
from ..config import get_settings

router = APIRouter(prefix="/api/stream", tags=["stream"])
settings = get_settings()

# Redis Pub/Sub チャンネル名
NOTIFICATION_CHANNEL = "task_notifications"

async def get_async_redis_client():
    """SSE専用の非同期Redisクライアント"""
    return await aioredis.from_url(settings.redis_url, decode_responses=True)

async def event_generator(request: Request):
    """
    SSEイベントジェネレーター
    非同期Redisを使用してサーバーをブロックせずに待機
    """
    client = await get_async_redis_client()
    pubsub = client.pubsub()
    await pubsub.subscribe(NOTIFICATION_CHANNEL)

    try:
        while True:
            # クライアント接続チェック
            if await request.is_disconnected():
                break

            # 非同期でメッセージを取得（ここでサーバー全体の処理を止めない）
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            
            if message and message["type"] == "message":
                data = message["data"]
                # decode_responses=Trueにしているのでbytes変換不要な場合が多いが念のため
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                
                # sse-starletteはdictを渡すと自動でフォーマットしてくれる
                yield {
                    "event": "message",
                    "data": data
                }
            else:
                # Keep-alive ping（データがない時だけ送る必要はないが、接続維持のため）
                # sse-starletteのping引数に任せる手もあるが、手動yieldの方が確実な場合も
                pass

            # ループのCPU占有を防ぐための微小待機
            await asyncio.sleep(0.1)

    except asyncio.CancelledError:
        print("SSE Client disconnected")
    except Exception as e:
        print(f"SSE Error: {e}")
    finally:
        await pubsub.unsubscribe(NOTIFICATION_CHANNEL)
        await pubsub.close()
        await client.aclose() # クライアントも閉じる

@router.get("/notifications")
async def stream_notifications(request: Request):
    """
    SSEによるリアルタイム通知ストリーム
    """
    return EventSourceResponse(
        event_generator(request),
        ping=15, # 自動Ping機能
        media_type="text/event-stream"
    )