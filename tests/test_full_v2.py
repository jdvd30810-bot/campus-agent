import sys
import subprocess
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.extractor import extract_campus_info
from app.apple_sync import add_to_apple_reminders, add_to_apple_calendar, parse_datetime

OCR_BIN = BASE_DIR / "app" / "ocr_bin"
OCR_SWIFT = BASE_DIR / "app" / "ocr.swift"
IMG_PATH = "/tmp/wechat_capture.png"

def run_e2e_v2():
    print("=" * 65)
    print("🚀 Campus-Agent RPA 2.0 视觉全自动端到端闭环测试")
    print("=" * 65)

    # 1. 识别屏幕
    print("1. 正在调用 Apple Vision 识别屏幕微信消息...")
    ocr_cmd = [str(OCR_BIN) if OCR_BIN.exists() else "swift", IMG_PATH]
    if not OCR_BIN.exists():
        ocr_cmd = ["swift", str(OCR_SWIFT), IMG_PATH]
    res = subprocess.run(ocr_cmd, capture_output=True, text=True)
    raw_text = res.stdout.strip()
    
    if len(raw_text) < 15:
        print("❌ 未在快照中发现有效文字，请先确保微信窗口展示了聊天内容。")
        return

    print(f"   ✅ 成功识别到 {len(raw_text)} 字符的屏幕文本！")
    print("   📄 原始屏幕文本摘录:")
    for line in raw_text.splitlines()[:5]:
        print(f"      > {line}")

    # 2. 移交 DeepSeek AI 大脑
    print("\n2. 正在交由 DeepSeek 大模型提炼待办事项与 DDL...")
    ai_res = extract_campus_info(raw_text)

    print(f"   ✅ AI 分析完毕！发现 {len(ai_res.todos)} 项待办，{len(ai_res.notifications)} 项通知。")
    print("\n【格式化简报】:\n" + ai_res.formatted_markdown)

    # 3. 自动同步 Apple 提醒事项 / 日历
    print("\n3. 正在自动同步至 Apple 官方「提醒事项」与「日历」...")
    synced = 0
    for todo in ai_res.todos:
        dt = parse_datetime(todo.due_datetime)
        notes = f"地点/平台: {todo.location or '未指定'}\n详情: {todo.action_item}\n来源: RPA 2.0 视觉巡查"
        if todo.is_calendar_event and dt:
            if add_to_apple_calendar(todo.title, dt, notes=notes):
                synced += 1
                print(f"   📅 已写入 Apple 日历: 【{todo.title}】 (时间: {dt})")
        else:
            if add_to_apple_reminders(todo.title, due_datetime=dt, notes=notes, priority=1, category=todo.category):
                synced += 1
                print(f"   ⏰ 已写入 Apple 提醒事项【{todo.category}】: 【{todo.title}】 (截止: {dt})")


    print(f"\n🎉 完美收官！共自动录入 {synced} 条待办到苹果系统！请拿出 iPhone 或打开 Mac 提醒事项查看！")

if __name__ == "__main__":
    run_e2e_v2()
