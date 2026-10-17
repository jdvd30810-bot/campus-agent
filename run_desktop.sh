#!/bin/bash
# Campus-Agent 独立桌面客户端快速拉起脚本
DIR="$(cd "$(dirname "$0")" && pwd)"
export CAMPUS_AGENT_ROOT="$DIR"

echo "🚀 正在启动 Campus-Agent 原生 macOS 独立桌面客户端..."
open "$DIR/bin/CampusAgent.app"
