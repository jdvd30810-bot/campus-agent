#!/bin/bash
# 停止奶蛙 (NaiWa) macOS 顶部状态栏常驻小胶囊

echo "⏹️ 正在停止奶蛙状态栏常驻胶囊..."
pkill -f "bin/naiwa_menubar"
if [ $? -eq 0 ]; then
    echo "✅ 奶蛙状态栏常驻胶囊已安全退出。"
else
    echo "ℹ️ 未发现正在运行的奶蛙状态栏胶囊进程。"
fi
