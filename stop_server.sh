#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ -f server.pid ]; then
    PID=$(cat server.pid)
    kill -9 "$PID" 2>/dev/null || true
    rm -f server.pid
fi
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
echo "Campus-Agent 已安全停止。"
