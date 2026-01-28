"""
Backend Startup Diagnostics Module
Phase 1: RAG Foundation
"""
import redis
from sqlalchemy import text
from .database import engine
from .config import get_settings

settings = get_settings()


def run_diagnostics() -> bool:
    """
    Run all startup diagnostics for backend service.

    Checks:
    1. Database connection and pgvector extension
    2. Redis connection

    Returns True if all checks pass.
    """
    print("=" * 40)
    print("[SYSTEM CHECK] STARTUP DIAGNOSTICS")
    print("=" * 40)

    all_ok = True

    # 1. Database Connection + pgvector Extension
    try:
        with engine.connect() as conn:
            # Basic connectivity
            conn.execute(text("SELECT 1"))

            # Check pgvector extension
            result = conn.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            has_pgvector = result.fetchone() is not None

            if has_pgvector:
                print("1. Database Connection ... [OK] (pgvector enabled)")
            else:
                print("1. Database Connection ... [WARN] (pgvector NOT enabled)")
                print("   -> Run: CREATE EXTENSION IF NOT EXISTS vector;")
                all_ok = False
    except Exception as e:
        print(f"1. Database Connection ... [FAIL] ({e})")
        all_ok = False

    # 2. Redis Connection
    try:
        r = redis.from_url(settings.redis_url)
        pong = r.ping()
        if pong:
            queue_len = r.llen("tasks")
            print(f"2. Redis Connection ...... [OK] (Queue length: {queue_len})")
        else:
            print("2. Redis Connection ...... [FAIL] (No PONG response)")
            all_ok = False
    except Exception as e:
        print(f"2. Redis Connection ...... [FAIL] ({e})")
        all_ok = False

    print("=" * 40)
    if all_ok:
        print("[OK] System is ready.")
    else:
        print("[WARN] Some checks failed. System may not work correctly.")
    print("=" * 40)

    return all_ok
