#!/bin/bash
set -e

echo "================================================================"
echo " NAK-BASE Integrated Backend Starting"
echo " (Backend API + Parser + Worker + Redis)"
echo "================================================================"

# 1. Start Redis (bound to localhost only - internal use)
echo "[1/4] Starting Redis..."
redis-server --daemonize yes --loglevel warning --bind 127.0.0.1
until redis-cli ping > /dev/null 2>&1; do
    echo "  Waiting for Redis..."
    sleep 1
done
echo "  Redis ready."

# 2. Start Parser service on port 8001
echo "[2/4] Starting Parser service..."
cd /parser && uvicorn app.main:app --host 0.0.0.0 --port 8001 &

# Brief wait so Parser is likely up before Worker starts
sleep 2

# 3. Start Worker
echo "[3/4] Starting Worker..."
cd /worker && python -m app.worker &

# 4. Start Backend API as main process (exec replaces shell, becomes PID 1)
echo "[4/4] Starting Backend API..."
cd /app && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
