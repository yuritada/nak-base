#!/usr/bin/env python3
"""
nak-base System Diagnosis Script (Backend)
==========================================
This script runs comprehensive system diagnostics from the Backend container.
Execute via: make test (in debug mode)

Checks performed:
1. Frontend/Parser network reachability
2. Database connection and statistics
3. Storage access and file count
4. Redis queue status and diagnostic task submission
"""

import os
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path

# Add app to path for imports
sys.path.insert(0, "/app")

import requests
import redis
from sqlalchemy import create_engine, text

# Configuration
LOG_FILE = "/app/logs/system_diagnosis.log"
FRONTEND_URL = "http://frontend:3000"
PARSER_URL = "http://parser:8001/health"
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nakbase:nakbase_secret@db:5432/nakbase")
STORAGE_PATH = os.getenv("STORAGE_PATH", "/storage")
TASK_QUEUE = "tasks"


class DiagnosticResult:
    """Container for diagnostic results"""

    def __init__(self):
        self.results = []
        self.all_passed = True

    def add(self, category: str, name: str, passed: bool, detail: str = ""):
        status = "OK" if passed else "NG"
        icon = "\u2705" if passed else "\u274c"
        self.results.append({
            "category": category,
            "name": name,
            "passed": passed,
            "status": f"{icon} {status}",
            "detail": detail
        })
        if not passed:
            self.all_passed = False

    def format_output(self) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"[DIAGNOSIS] {timestamp}",
            "-" * 48
        ]

        for r in self.results:
            detail = f" ({r['detail']})" if r['detail'] else ""
            lines.append(f"[{r['category']}] {r['name']:<22}: {r['status']}{detail}")

        lines.append("-" * 48)
        if self.all_passed:
            lines.append("RESULT: ALL SYSTEMS GO")
        else:
            lines.append("RESULT: SOME CHECKS FAILED")
        lines.append("")

        return "\n".join(lines)


def check_frontend(diag: DiagnosticResult):
    """Check 1a: Frontend reachability"""
    try:
        response = requests.get(FRONTEND_URL, timeout=5)
        diag.add("BE", "Frontend Reachability", True)
    except requests.RequestException as e:
        diag.add("BE", "Frontend Reachability", False, str(e)[:30])


def check_parser(diag: DiagnosticResult):
    """Check 1b: Parser reachability"""
    try:
        response = requests.get(PARSER_URL, timeout=5)
        if response.status_code == 200:
            diag.add("BE", "Parser Reachability", True)
        else:
            diag.add("BE", "Parser Reachability", False, f"HTTP {response.status_code}")
    except requests.RequestException as e:
        diag.add("BE", "Parser Reachability", False, str(e)[:30])


def check_database(diag: DiagnosticResult):
    """Check 2: Database connection and statistics"""
    try:
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            # Check pgvector extension
            pgvector_result = conn.execute(
                text("SELECT * FROM pg_extension WHERE extname = 'vector'")
            ).fetchone()
            pgvector_ok = pgvector_result is not None
            diag.add("BE", "DB Connection (Vector)", pgvector_ok,
                     "pgvector enabled" if pgvector_ok else "pgvector NOT found")

            # Get table count
            table_count = conn.execute(
                text("""
                    SELECT COUNT(*) FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                """)
            ).scalar()

            # Get record counts for key tables
            stats = {}
            for table in ["users", "papers", "inference_tasks"]:
                try:
                    count = conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                    stats[table] = count
                except Exception:
                    stats[table] = "N/A"

            stats_str = f"Tables: {table_count} | Users: {stats['users']}, Papers: {stats['papers']}, Tasks: {stats['inference_tasks']}"
            diag.add("BE", "DB Stats", True, f"\U0001F4CA {stats_str}")

    except Exception as e:
        diag.add("BE", "DB Connection (Vector)", False, str(e)[:40])
        diag.add("BE", "DB Stats", False, "Connection failed")


def check_storage(diag: DiagnosticResult):
    """Check 3: Storage access and file count"""
    try:
        storage_path = Path(STORAGE_PATH)

        # Check if directory exists and is writable
        if not storage_path.exists():
            storage_path.mkdir(parents=True, exist_ok=True)

        # Test write access
        test_file = storage_path / ".diagnosis_test"
        test_file.write_text("test")
        test_file.unlink()

        # Count files (excluding hidden files)
        file_count = len([f for f in storage_path.iterdir() if f.is_file() and not f.name.startswith(".")])

        diag.add("BE", "Storage Access", True, f"Files: {file_count}")
    except Exception as e:
        diag.add("BE", "Storage Access", False, str(e)[:30])


def check_redis_and_submit_task(diag: DiagnosticResult) -> str:
    """Check 4: Redis queue status and submit diagnostic task"""
    task_id = f"diag_{uuid.uuid4().hex[:8]}"

    try:
        client = redis.from_url(REDIS_URL)
        client.ping()

        # Get current queue length
        queue_length_before = client.llen(TASK_QUEUE)

        # Submit diagnostic task
        diagnostic_task = json.dumps({
            "type": "SYSTEM_DIAGNOSIS",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat()
        })
        client.rpush(TASK_QUEUE, diagnostic_task)

        # Get new queue length
        queue_length_after = client.llen(TASK_QUEUE)

        diag.add("BE", "Redis Status", True,
                 f"Queue Length: {queue_length_before} -> {queue_length_after}")

        return task_id

    except Exception as e:
        diag.add("BE", "Redis Status", False, str(e)[:30])
        return ""


def write_log(content: str):
    """Write diagnostic results to log file"""
    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(content)
        f.write("\n")


def main():
    print("=" * 50)
    print(" NAK-BASE SYSTEM DIAGNOSIS (Backend)")
    print("=" * 50)

    diag = DiagnosticResult()

    # Run all checks
    print("\n[1/4] Checking Frontend connectivity...")
    check_frontend(diag)

    print("[2/4] Checking Parser connectivity...")
    check_parser(diag)

    print("[3/4] Checking Database...")
    check_database(diag)

    print("[4/4] Checking Storage...")
    check_storage(diag)

    print("[5/5] Checking Redis and submitting diagnostic task...")
    task_id = check_redis_and_submit_task(diag)

    # Format and output results
    output = diag.format_output()
    print("\n" + output)

    # Write to log file
    write_log(output)
    print(f"Results written to: {LOG_FILE}")

    if task_id:
        print(f"\nDiagnostic task submitted: {task_id}")
        print("Worker should process this and append results to the log.")

    # Exit with appropriate code
    sys.exit(0 if diag.all_passed else 1)


if __name__ == "__main__":
    main()
