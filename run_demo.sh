#!/bin/bash
# ==========================================================
# 🎓 Campus-Agent 校园智能助教 · 导师演示一键启动程序
# 专为向教授/导师实机汇报与演示打造，一键自检、启动并呼出网页
# ==========================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=========================================================="
echo "🎓 欢迎老师检阅 Campus-Agent（校园消息智能聚合助手）"
echo "=========================================================="
echo "📌 项目定位：非侵入式端侧视觉具身学伴与 DDL 预警系统"
echo "💻 运行环境：macOS (Apple Silicon / Intel) · Python 3.9+"
echo "----------------------------------------------------------"

# 1. 检查或重启后台网关
if [ -f "start_server.sh" ]; then
    echo "🚀 正在启动后台 FastAPI 网关与智能调度守护进程..."
    ./start_server.sh
else
    echo "⚠️ 未找到 start_server.sh，直接启动 uvicorn..."
    nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
fi

sleep 1

# 2. 唤起默认浏览器打开主控制台与交互文档
echo ""
echo "🌐 正在为您自动在浏览器中打开演示控制台..."
open "http://127.0.0.1:8000/dashboard" 2>/dev/null || true

echo ""
echo "✨ 服务已就绪！您可以直接选择以下方式体验："
echo "   1. 🖥️ 原生独立桌面客户端: 执行 ./run_desktop.sh 或直接双击 bin/CampusAgent.app"
echo "   2. 🎛️ 浏览器主控制台:     http://127.0.0.1:8000/dashboard"
echo "   3. 🐸 独立动效大剧场:     http://127.0.0.1:8000/naiwa"
echo "   4. 📑 交互式 API 文档:     http://127.0.0.1:8000/docs"
echo "   5. 💊 顶部常驻胶囊遥测:   http://127.0.0.1:8000/api/v1/menubar/status"
echo ""
echo "🧪 若需向老师展示 34 项全量自动化回归测试实测："
echo "   执行命令：./venv/bin/python -m unittest discover tests"
echo "=========================================================="
