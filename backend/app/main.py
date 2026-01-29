"""
nak-base FastAPI メインアプリケーション
Phase 1-1: DB診断機能付き
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from .routers import auth, papers, stream, conferences
from .services.queue_service import get_queue_length
from .database import engine, Base
from .config import get_settings


def print_banner(title: str, status: str, symbol: str = "=") -> None:
    """Print a formatted banner to console"""
    width = 60
    print(f"\n{symbol * width}")
    print(f"{title.center(width)}")
    print(f"{status.center(width)}")
    print(f"{symbol * width}\n")


def run_db_diagnostics() -> dict:
    """
    Run database diagnostics at startup:
    1. Connection check
    2. pgvector extension check
    3. Critical tables existence check
    """
    results = {
        "connection": {"status": "NG", "message": ""},
        "pgvector": {"status": "NG", "message": ""},
        "tables": {"status": "NG", "message": "", "found": [], "missing": []}
    }

    critical_tables = ["users", "papers", "versions", "files", "embeddings", "inference_tasks", "feedbacks"]

    try:
        with engine.connect() as conn:
            # 1. Connection check
            conn.execute(text("SELECT 1"))
            results["connection"]["status"] = "OK"
            results["connection"]["message"] = "Database connection successful"

            # 2. pgvector extension check
            pgvector_result = conn.execute(
                text("SELECT * FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()

            if pgvector_result:
                results["pgvector"]["status"] = "OK"
                results["pgvector"]["message"] = "pgvector extension is enabled"
            else:
                results["pgvector"]["message"] = "pgvector extension NOT found"

            # 3. Tables existence check
            tables_result = conn.execute(
                text("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    AND table_type = 'BASE TABLE'
                """)
            ).fetchall()

            existing_tables = {row[0] for row in tables_result}

            for table in critical_tables:
                if table in existing_tables:
                    results["tables"]["found"].append(table)
                else:
                    results["tables"]["missing"].append(table)

            if not results["tables"]["missing"]:
                results["tables"]["status"] = "OK"
                results["tables"]["message"] = f"All {len(critical_tables)} critical tables exist"
            else:
                results["tables"]["message"] = f"Missing tables: {', '.join(results['tables']['missing'])}"

    except OperationalError as e:
        results["connection"]["message"] = f"Connection failed: {str(e)}"
    except Exception as e:
        results["connection"]["message"] = f"Unexpected error: {str(e)}"

    return results


def print_diagnostics_report(results: dict) -> None:
    """Print formatted diagnostics report to console"""
    print("\n" + "=" * 60)
    print(" NAK-BASE DATABASE DIAGNOSTICS ".center(60, "="))
    print("=" * 60)

    # Connection status
    conn_status = results["connection"]["status"]
    conn_icon = "[OK]" if conn_status == "OK" else "[NG]"
    print(f"\n  1. DB Connection:     {conn_icon} {results['connection']['message']}")

    # pgvector status
    pgv_status = results["pgvector"]["status"]
    pgv_icon = "[OK]" if pgv_status == "OK" else "[NG]"
    print(f"  2. pgvector:          {pgv_icon} {results['pgvector']['message']}")

    # Tables status
    tbl_status = results["tables"]["status"]
    tbl_icon = "[OK]" if tbl_status == "OK" else "[NG]"
    print(f"  3. Critical Tables:   {tbl_icon} {results['tables']['message']}")

    if results["tables"]["found"]:
        print(f"     Found: {', '.join(results['tables']['found'])}")
    if results["tables"]["missing"]:
        print(f"     Missing: {', '.join(results['tables']['missing'])}")

    # Overall status
    all_ok = all(
        results[key]["status"] == "OK"
        for key in ["connection", "pgvector", "tables"]
    )

    print("\n" + "-" * 60)
    if all_ok:
        print(" OVERALL STATUS: [OK] Database is ready! ".center(60, "*"))
    else:
        print(" OVERALL STATUS: [NG] Database needs attention ".center(60, "!"))
    print("-" * 60 + "\n")


def create_pgvector_extension() -> bool:
    """Create pgvector extension if it doesn't exist"""
    try:
        with engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
            print("  -> pgvector extension created/verified")
            return True
    except Exception as e:
        print(f"  -> Failed to create pgvector extension: {e}")
        return False


def run_migrations() -> bool:
    """Run Alembic migrations programmatically"""
    try:
        from alembic.config import Config
        from alembic import command
        import os

        # Get the path to alembic.ini
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        alembic_ini_path = os.path.join(backend_dir, "alembic.ini")

        if os.path.exists(alembic_ini_path):
            alembic_cfg = Config(alembic_ini_path)
            alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
            alembic_cfg.set_main_option("sqlalchemy.url", get_settings().database_url)

            print("  -> Running Alembic migrations...")
            command.upgrade(alembic_cfg, "head")
            print("  -> Migrations completed successfully")
            return True
        else:
            print(f"  -> alembic.ini not found at {alembic_ini_path}")
            return False
    except Exception as e:
        print(f"  -> Migration error: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown events"""
    settings = get_settings()

    print_banner("NAK-BASE API STARTING", f"Debug Mode: {settings.debug_mode}")

    # Step 1: Create pgvector extension
    print("  [STARTUP] Step 1: Creating pgvector extension...")
    create_pgvector_extension()

    # Step 2: Run migrations
    print("  [STARTUP] Step 2: Running database migrations...")
    run_migrations()

    # Step 3: Run diagnostics
    print("  [STARTUP] Step 3: Running database diagnostics...")
    diagnostics = run_db_diagnostics()
    print_diagnostics_report(diagnostics)

    yield

    # Shutdown
    print_banner("NAK-BASE API SHUTTING DOWN", "Goodbye!")


app = FastAPI(
    title="nak-base API",
    description="論文フィードバックシステム - Phase 1.5 SSE対応",
    version="1.5.0",
    lifespan=lifespan
)

# CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://frontend:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(papers.router)
app.include_router(stream.router)
app.include_router(conferences.router)


@app.get("/")
def root():
    """Health check endpoint."""
    return {
        "service": "nak-base API",
        "status": "running",
        "version": "1.5.0",
        "phase": "1.5 SSE Support"
    }


@app.get("/health")
def health_check():
    """Detailed health check."""
    return {
        "status": "healthy",
        "queue_length": get_queue_length()
    }


@app.get("/diagnostics")
def get_diagnostics():
    """Run and return database diagnostics."""
    return run_db_diagnostics()
