#!/usr/bin/env python3
"""
nak-base Worker Diagnostic Module
=================================
This module is dynamically imported by the Worker when processing
SYSTEM_DIAGNOSIS tasks in debug mode.

NOT included in production builds.
"""

import os
import requests
from datetime import datetime
from pathlib import Path

LOG_FILE = "/app/logs/system_diagnosis.log"
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")


def write_log(content: str):
    """Append to the shared diagnostic log file"""
    log_path = Path(LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(content)


def check_ollama_connection() -> tuple[bool, str]:
    """
    Check 6: Verify connection to Ollama LLM service
    Returns: (success: bool, detail: str)
    """
    try:
        # Try to get the list of available models
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)

        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])

            if models:
                # Get first model name
                model_name = models[0].get("name", "unknown")
                return True, f"Model: {model_name}"
            else:
                return True, "No models loaded"
        else:
            return False, f"HTTP {response.status_code}"

    except requests.Timeout:
        return False, "Timeout"
    except requests.ConnectionError:
        return False, "Connection refused"
    except Exception as e:
        return False, str(e)[:30]


def run_worker_diagnosis(task_data: dict) -> dict:
    """
    Main entry point for worker diagnosis.
    Called by worker.py when SYSTEM_DIAGNOSIS task is received.

    Args:
        task_data: The diagnostic task payload from Redis

    Returns:
        dict with diagnosis results
    """
    task_id = task_data.get("task_id", "unknown")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    results = []

    # Check 5: Task Receipt confirmation
    results.append({
        "check": "Task Receipt",
        "passed": True,
        "detail": f"TaskID: {task_id}"
    })

    # Check 6: Ollama/LLM connection
    ollama_ok, ollama_detail = check_ollama_connection()
    results.append({
        "check": "LLM Connection",
        "passed": ollama_ok,
        "detail": ollama_detail
    })

    # Format log output
    log_lines = []
    all_passed = True

    for r in results:
        icon = "\u2705" if r["passed"] else "\u274c"
        status = "OK" if r["passed"] else "NG"
        detail = f" ({r['detail']})" if r["detail"] else ""
        log_lines.append(f"[WK] {r['check']:<22}: {icon} {status}{detail}")
        if not r["passed"]:
            all_passed = False

    # Write to shared log
    log_content = "\n".join(log_lines) + "\n"
    write_log(log_content)

    # Also print to worker stdout for visibility
    print("\n" + "=" * 40)
    print(" WORKER DIAGNOSIS RESULTS")
    print("=" * 40)
    for line in log_lines:
        print(line)
    print("=" * 40 + "\n")

    return {
        "task_id": task_id,
        "timestamp": timestamp,
        "all_passed": all_passed,
        "results": results
    }
