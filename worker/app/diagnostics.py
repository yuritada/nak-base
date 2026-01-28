"""
Worker Startup Diagnostics Module
Phase 1: RAG Foundation
"""
import redis
import requests
from sqlalchemy import text
from .database import engine
from .config import get_settings

settings = get_settings()


def run_diagnostics() -> bool:
    """
    Run all startup diagnostics for worker service.

    Checks:
    1. Database connection and pgvector extension
    2. Redis connection
    3. Parser service connectivity
    4. Ollama service connectivity (embedding)

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

    # 3. Parser Service
    try:
        resp = requests.get(f"{settings.parser_url}/health", timeout=10)
        if resp.status_code == 200:
            print(f"3. Parser Service ........ [OK] ({settings.parser_url}/health)")
        else:
            print(f"3. Parser Service ........ [WARN] (status={resp.status_code})")
            all_ok = False
    except requests.exceptions.ConnectionError:
        print(f"3. Parser Service ........ [WAIT] (Not yet available)")
        # Don't fail - parser might start later
    except Exception as e:
        print(f"3. Parser Service ........ [FAIL] ({e})")
        all_ok = False

    # 4. Ollama Service (Embedding)
    try:
        if settings.mock_mode:
            print(f"4. Ollama Service ........ [SKIP] (Mock mode enabled)")
        else:
            # Try to generate a test embedding
            resp = requests.post(
                f"{settings.ollama_url}/api/embeddings",
                json={"model": settings.embedding_model, "prompt": "test"},
                timeout=30
            )
            if resp.status_code == 200:
                embedding = resp.json().get("embedding", [])
                dim = len(embedding)
                print(f"4. Ollama Service ........ [OK] (Response dim: {dim})")
                if dim != settings.embedding_dim:
                    print(f"   [WARN] Expected dim={settings.embedding_dim}, got {dim}")
            else:
                print(f"4. Ollama Service ........ [WARN] (status={resp.status_code})")
                print(f"   -> Run: ollama pull {settings.embedding_model}")
                all_ok = False
    except requests.exceptions.ConnectionError:
        print(f"4. Ollama Service ........ [WAIT] (Not yet available)")
        # Don't fail - ollama might start later
    except Exception as e:
        print(f"4. Ollama Service ........ [FAIL] ({e})")
        all_ok = False

    print("=" * 40)
    if all_ok:
        print("[OK] System is ready.")
    else:
        print("[WARN] Some checks failed. System may not work correctly.")
    print("=" * 40)

    return all_ok
