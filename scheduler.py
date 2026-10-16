#!/usr/bin/env python3
"""
Campus-Agent - 智能定时巡检与高危 DDL 预警后台守护进程 (scheduler.py)
-------------------------------------------------------------------
特性：
1. 【智能空闲感知避让 (Idle-Aware Adaptive Yielding)】：
   用户在活跃操作电脑时（idle < 45s），绝不移动鼠标或干扰屏幕，主动挂起避让；
   用户离开座位/空闲超 45 秒时，再静默启动后台显存抓取与快速巡检；
2. 【高危 DDL 声光双重预警】：
   发现 24 小时内临近截止或高优作业，自动推送 macOS 原生横幅通知 + Mac 硬件扬声器奶龙语音大声提醒；
3. 【苹果原生生态自动写入】：
   自动写入系统提醒事项与日历，并通过 iCloud 实时同步到学生手机端。
"""

import sys
import time
import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.scheduler_daemon import daemon_scheduler

def main():
    print("=" * 70)
    print("🤖 Campus-Agent 智能空闲感知守护进程已就绪！")
    print("🛡️ 【防抢占承诺】：用户在电脑前敲字时绝不移动鼠标；离席超 45s 方静默工作。")
    print("🚨 【高危预警】：24h 临近截止待办自动触发 macOS 原生横幅 + 硬件扬声器语音！")
    print("💡 控制台地址: http://127.0.0.1:8000/dashboard")
    print("=" * 70)

    while True:
        try:
            status = daemon_scheduler.get_status()
            idle_secs = status["current_idle_seconds"]
            interval = status["interval_minutes"]

            # 执行一轮周期判断
            res = daemon_scheduler.patrol_cycle(force=False)
            cycle_status = res.get("status")

            if cycle_status == "yielding":
                print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] [智能避让] 用户正在活跃操作电脑 (物理空闲 {idle_secs:.1f}s < 45s)，守护器主动挂起让出...")
            elif cycle_status == "success":
                summary = res.get("summary", {})
                print(f"✅ [{datetime.now().strftime('%H:%M:%S')}] [巡检完成] 扫描 {summary.get('inspected_count')} 个群，同步 {summary.get('synced_count')} 项待办，高危预警 {summary.get('urgent_count')} 项！")
            elif cycle_status == "waiting_interval":
                pass
            elif cycle_status == "disabled":
                print(f"⏸️ [{datetime.now().strftime('%H:%M:%S')}] 后台守护巡查当前已暂停")

            time.sleep(15)  # 每 15 秒轮询一次
        except KeyboardInterrupt:
            print("\n👋 调度守护器已安全退出。")
            break
        except Exception as e:
            print(f"⚠️ 调度守护器异常: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
