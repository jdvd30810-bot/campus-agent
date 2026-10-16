#!/bin/bash
# 启动奶蛙 (NaiWa) macOS 顶部状态栏常驻小胶囊

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
cd "$DIR"

echo "🐸 正在检查并编译奶蛙状态栏胶囊应用..."
mkdir -p bin
clang -framework Cocoa -O2 -o bin/naiwa_menubar src/menubar/naiwa_menubar.m

if [ $? -ne 0 ]; then
    echo "❌ 编译失败，请检查 Xcode Command Line Tools"
    exit 1
fi

# 打包为 macOS 原生 App Bundle (包含 LSUIElement=YES，确保系统状态栏识别并显示)
mkdir -p bin/NaiWaMenuBar.app/Contents/MacOS
cp bin/naiwa_menubar bin/NaiWaMenuBar.app/Contents/MacOS/

cat << 'EOF' > bin/NaiWaMenuBar.app/Contents/Info.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>naiwa_menubar</string>
    <key>CFBundleIdentifier</key>
    <string>com.campus.naiwa.menubar</string>
    <key>CFBundleName</key>
    <string>奶蛙</string>
    <key>CFBundleDisplayName</key>
    <string>奶蛙守护胶囊</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# 检查是否已在运行
PID=$(pgrep -f "naiwa_menubar")
if [ -n "$PID" ]; then
    echo "⚠️ 奶蛙状态栏常驻胶囊已在运行中 (PID: $PID)"
    echo "提示: 请看 Mac 屏幕最右上角（控制中心/Wi-Fi/时钟附近）的 🐸 奶蛙 图标。"
    exit 0
fi

echo "🚀 正在通过 macOS LaunchServices 载入状态栏胶囊..."
open bin/NaiWaMenuBar.app 2>/dev/null || nohup ./bin/NaiWaMenuBar.app/Contents/MacOS/naiwa_menubar > /dev/null 2>&1 &

sleep 0.5
NEW_PID=$(pgrep -f "naiwa_menubar")
echo "✅ 奶蛙状态栏常驻胶囊已成功运行 (PID: $NEW_PID)！"
echo "👉 请查看 Mac 屏幕右上角菜单栏的 🐸 图标（位于时钟/Wi-Fi/控制中心左侧）。"
echo "💡 若为刘海屏 MacBook 且前台应用菜单过长，切换到访达(Finder)即可看到。"
