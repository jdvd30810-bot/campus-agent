import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.apple_sync import add_to_apple_reminders, add_to_apple_calendar

def test_sync():
    print("=" * 60)
    print("🍏 正在测试 Apple 官方「提醒事项」与「日历」写入功能...")
    print("=" * 60)

    # 1. 测试写入提醒事项（带截止时间闹钟）
    due = datetime.now() + timedelta(days=2, hours=3)
    title_rem = "【测试】提交《操作系统》课程设计报告"
    notes_rem = "提交平台：超星学习通\n要求：附带演示视频\n由 Campus-Agent 自动提取创建"

    print(f"1. 尝试向 Apple「提醒事项」创建待办: {title_rem}")
    ok1 = add_to_apple_reminders(title_rem, due_datetime=due, notes=notes_rem, priority=1)
    if ok1:
        print(f"   ✅ 成功写入提醒事项！截止时间设置为: {due.strftime('%Y-%m-%d %H:%M')}")
    else:
        print("   ❌ 写入提醒事项失败，请确认系统权限。")

    # 2. 测试写入日历日程（带会议/讲座闹钟）
    cal_start = datetime.now() + timedelta(days=1, hours=2)
    title_cal = "【测试讲座】AI智能体与大模型前沿分享"
    notes_cal = "地点：东阶梯教室301\n由 Campus-Agent 自动提取创建"

    print(f"\n2. 尝试向 Apple「日历」创建日程: {title_cal}")
    ok2 = add_to_apple_calendar(title_cal, start_datetime=cal_start, duration_minutes=90, notes=notes_cal)
    if ok2:
        print(f"   ✅ 成功写入日历日程！开始时间设置为: {cal_start.strftime('%Y-%m-%d %H:%M')}")
    else:
        print("   ❌ 写入日历失败。")

    print("\n👉 现在请打开你的 Mac 官方自带的「提醒事项 (Reminders)」和「日历 (Calendar)」App，查看刚才生成的条目！")

if __name__ == "__main__":
    test_sync()
