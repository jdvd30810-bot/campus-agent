#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# 清理已有的 8000 端口占用
if [ -f server.pid ]; then
    OLD_PID=$(cat server.pid)
    kill -0 "$OLD_PID" 2>/dev/null && kill -9 "$OLD_PID" 2>/dev/null
    rm -f server.pid
fi
lsof -ti :8000 | xargs kill -9 2>/dev/null || true

# 后台常驻启动 FastAPI uvicorn 网关
nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
echo $! > server.pid

sleep 1
if lsof -i :8000 >/dev/null 2>&1; then
    echo "Campus-Agent 启动成功！PID: $(cat server.pid)"
    echo "本机控制台网址: http://127.0.0.1:8000/dashboard"
else
    echo "Campus-Agent 启动失败，请检查 server.log"
    cat server.log
fi
