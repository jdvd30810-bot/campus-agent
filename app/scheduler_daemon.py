import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("campus-agent.daemon")

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.human_driver import get_system_idle_seconds
from app.groups_manager import load_group_config, save_group_config
from app.agent import send_macos_notification

class CampusDaemonScheduler:
    """
    【Campus-Agent 智能后台守护调度器】
    核心能力：
    1. 定时自动巡查（按 interval_minutes 执行，支持 15/30/60/120 分钟）；
    2. 物理空闲感知避让（Idle-Aware Yielding）：用户活跃时（idle < 45s）绝不抢占鼠标，主动挂起；
    3. 高危 DDL 判定器（Urgent DDL Sieve）：24h 内临近截止或高优作业判定；
    4. 声光双重预警管道：macOS 原生横幅通知 + Mac 物理硬件扬声器奶龙原声大叫与语音口播！
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.is_enabled: bool = True
        self.idle_threshold_seconds: float = 45.0
        self.is_patrolling: bool = False
        self.last_status: str = "idle"  # idle, yielding, patrolling, success, error
        self.last_result_summary: Dict[str, Any] = {}
        self.urgent_alerts_history: List[Dict[str, Any]] = []
        self._sync_config_from_file()

    def _sync_config_from_file(self):
        """从 monitored_groups.json 同步配置"""
        cfg = load_group_config()
        self.interval_minutes = int(cfg.get("interval_minutes", 30))
        self.last_inspected_at = cfg.get("last_inspected_at")
        if "daemon_enabled" in cfg:
            self.is_enabled = bool(cfg.get("daemon_enabled"))

    def check_is_urgent_todo(self, todo: Dict[str, Any]) -> Tuple[bool, str, float]:
        """
        高危 DDL 智能判定引擎：
        判定标准：
        1. 24 小时内截止的待办 (0 <= hours_left <= 24.0) -> 高危 🚨
        2. 刚刚截止 6 小时以内的待办 (-6.0 <= hours_left < 0) -> 逾期预警 ⚠️
        3. priority == 'HIGH' 且 48 小时内截止 -> 重点预警 🔔
        4. 课程大作业/实验报告/期末考且 36 小时内截止 -> 课程预警 📚
        返回: (is_urgent, reason, hours_left)
        """
        due_str = todo.get("due_datetime")
        title = todo.get("title", "未命名待办")
        priority = (todo.get("priority") or "NORMAL").upper()
        category = todo.get("category", "course")

        if not due_str:
            # 没有明确截止时间的待办不作为高危对待
            return False, "无截止时间", 999.0

        due_dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
            try:
                due_dt = datetime.strptime(due_str.strip(), fmt)
                break
            except Exception:
                continue

        if not due_dt:
            return False, "时间格式无法解析", 999.0

        now = datetime.now()
        hours_left = (due_dt - now).total_seconds() / 3600.0

        if -6.0 <= hours_left < 0:
            return True, f"已于 {abs(hours_left):.1f} 小时前截止，请尽快确认是否补交！", hours_left

        if 0 <= hours_left <= 24.0:
            return True, f"临近最后截止，仅剩 {hours_left:.1f} 小时！", hours_left

        if priority == "HIGH" and hours_left <= 48.0:
            return True, f"官方高优事项 (HIGH) 且在 48 小时内截止（剩余 {hours_left:.1f}h）", hours_left

        if category == "course" and any(k in title for k in ["大作业", "实验", "报告", "期末", "考试", "答辩"]) and hours_left <= 36.0:
            return True, f"核心课程节点，剩余 {hours_left:.1f} 小时", hours_left

        return False, "非高危待办", hours_left

    def trigger_urgent_ddl_alert(self, urgent_todos: List[Dict[str, Any]], group_name: str = "微信群") -> Dict[str, Any]:
        """
        触发高危 DDL 声光双重预警：
        1. 推送 macOS 原生横幅通知（带 Glass 警示音）；
        2. Mac 硬件扬声器物理发声（播放 nailong_alert.wav + 奶龙语音朗读）。
        """
        if not urgent_todos:
            return {"status": "skipped", "message": "无高危待办"}

        top_todo = urgent_todos[0]
        title_str = top_todo.get("title", "待办事项")
        due_str = top_todo.get("due_datetime", "近期")
        speaker = top_todo.get("speaker", "发布人")
        reason = top_todo.get("urgent_reason", "临近截止")

        # 1. 组装并发送 macOS 原生系统横幅通知
        banner_title = "🚨 奶蛙高危 DDL 预警！"
        banner_subtitle = f"【{title_str}】{reason}"
        banner_body = f"来源: {group_name} · 发布人: {speaker} · 截止: {due_str}"
        send_macos_notification(banner_title, banner_subtitle, banner_body, sound="Glass")
        logger.info(f"📢 [Mac 横幅通知已推送] {banner_title} - {banner_subtitle}")

        # 2. 预警文案（纯静默记录，彻底停用任何音频播放）
        speech_script = f"紧急预警！高危待办【{title_str}】{reason}，快去查看苹果提醒事项！吧哈哈哈哈！"

        # 3. 记入预警流水审计历史
        record = {
            "id": f"urgent_{int(time.time() * 1000)}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "title": title_str,
            "due_datetime": due_str,
            "category": top_todo.get("category", "course"),
            "urgent_reason": reason,
            "group_name": group_name,
            "spoken_script": speech_script,
            "count": len(urgent_todos)
        }
        self.urgent_alerts_history.insert(0, record)
        if len(self.urgent_alerts_history) > 20:
            self.urgent_alerts_history.pop()

        return {"status": "alerted", "record": record}

    def test_simulate_alert(self) -> Dict[str, Any]:
        """
        一键模拟触发高危 DDL 预警：用于用户在控制台现场体验与测试 Mac 原生横幅及硬件声音
        """
        mock_urgent_todo = {
            "title": "计算机系统大作业线上提交",
            "due_datetime": (datetime.now() + timedelta(hours=3.5)).strftime("%Y-%m-%d %H:%M:%S"),
            "category": "course",
            "priority": "HIGH",
            "speaker": "系统结构张教授",
            "urgent_reason": "临近最后截止，仅剩 3.5 小时！"
        }
        return self.trigger_urgent_ddl_alert([mock_urgent_todo], group_name="2026系统结构核心课程群")

    def patrol_cycle(self, force: bool = False) -> Dict[str, Any]:
        """
        执行一轮智能守护巡查：
        1. 检查启用开关；
        2. 检查巡查周期（若未到期且非 force 则跳过）；
        3. 检查物理外设空闲时间（若 idle < 45s 且非 force 则主动让出挂起）；
        4. 执行已订阅微信群后台静默漫游巡查；
        5. 过滤提取出所有高危 DDL 并触发声光预警。
        """
        if self.is_patrolling:
            return {"status": "busy", "message": "上一轮微信群巡查尚未结束，请稍候"}

        self._sync_config_from_file()

        if not self.is_enabled and not force:
            self.last_status = "disabled"
            return {"status": "disabled", "message": "后台定时守护巡检当前已由用户暂停"}

        # 检查时间周期
        now = datetime.now()
        time_due = False
        if not self.last_inspected_at:
            time_due = True
        else:
            try:
                last_dt = datetime.strptime(self.last_inspected_at, "%Y-%m-%d %H:%M:%S")
                next_dt = last_dt + timedelta(minutes=self.interval_minutes)
                time_due = (now >= next_dt)
            except Exception:
                time_due = True

        if not time_due and not force:
            self.last_status = "waiting_interval"
            return {"status": "waiting_interval", "message": f"巡查周期尚未到达（每 {self.interval_minutes} 分钟一次）"}

        # 检查物理空闲
        idle_secs = get_system_idle_seconds()
        if idle_secs < self.idle_threshold_seconds and not force:
            self.last_status = "yielding"
            logger.info(f"⏳ [智能避让] 用户正活跃使用电脑 (物理空闲 {idle_secs:.1f}s < 45s)，守护器主动挂起让出，绝不抢占鼠标！")
            return {
                "status": "yielding",
                "idle_seconds": idle_secs,
                "threshold": self.idle_threshold_seconds,
                "message": f"检测到用户正在活跃操作电脑 (物理空闲 {idle_secs:.1f}s < 45s)，守护器主动避让挂起"
            }

        # 启动巡查
        self.is_patrolling = True
        self.last_status = "patrolling"
        logger.info(f"⚡ [守护巡查启动] 用户物理空闲 {idle_secs:.1f}s，开始后台静默巡检...")

        try:
            from app.rpa import execute_batch_inspection
            res = execute_batch_inspection(max_scroll_pages=2, force=force)
            
            # 扫描所有新同步待办中的高危项
            urgent_found = []
            if isinstance(res, dict):
                results = res.get("results", [])
                for group_res in results:
                    group_name = group_res.get("group_name", "校园群")
                    for todo in group_res.get("todos", []):
                        is_urgent, reason, hours = self.check_is_urgent_todo(todo)
                        if is_urgent:
                            todo_copy = dict(todo)
                            todo_copy["urgent_reason"] = reason
                            todo_copy["hours_left"] = hours
                            todo_copy["source_group"] = group_name
                            urgent_found.append(todo_copy)

            # 若发现高危 DDL，触发声光双重预警
            if urgent_found:
                logger.warning(f"🚨 [检测到高危 DDL] 发现 {len(urgent_found)} 项紧急待办，立即触发声光预警！")
                self.trigger_urgent_ddl_alert(urgent_found, group_name=urgent_found[0].get("source_group", "微信群"))
            elif isinstance(res, dict) and res.get("total_synced_todos", 0) > 0:
                # 普通待办提醒
                send_macos_notification("🐸 奶蛙校园巡视简报", f"已录入 {res.get('total_synced_todos')} 项新待办", "所有事项已安全写入 Apple 提醒事项/日历")

            self.last_inspected_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.last_status = "success"
            self.last_result_summary = {
                "timestamp": self.last_inspected_at,
                "inspected_count": res.get("inspected_count", 0) if isinstance(res, dict) else 0,
                "synced_count": res.get("total_synced_todos", 0) if isinstance(res, dict) else 0,
                "urgent_count": len(urgent_found)
            }

            # 存盘更新 last_inspected_at
            cfg = load_group_config()
            cfg["last_inspected_at"] = self.last_inspected_at
            save_group_config(cfg)

            return {
                "status": "success",
                "message": f"巡查成功完成！扫描 {self.last_result_summary['inspected_count']} 群，录入 {self.last_result_summary['synced_count']} 待办，高危 DDL: {len(urgent_found)} 项",
                "summary": self.last_result_summary,
                "urgent_todos": urgent_found
            }

        except Exception as e:
            logger.error(f"守护巡查执行异常: {e}", exc_info=True)
            self.last_status = "error"
            return {"status": "error", "message": f"巡检异常: {str(e)}"}
        finally:
            self.is_patrolling = False

    def get_status(self) -> Dict[str, Any]:
        """获取当前后台守护调度器的全量遥测状态"""
        self._sync_config_from_file()
        idle_secs = get_system_idle_seconds()

        # 计算下一次预估运行时间
        next_eta = "即将执行"
        if self.last_inspected_at:
            try:
                last_dt = datetime.strptime(self.last_inspected_at, "%Y-%m-%d %H:%M:%S")
                next_dt = last_dt + timedelta(minutes=self.interval_minutes)
                if next_dt > datetime.now():
                    diff_min = int((next_dt - datetime.now()).total_seconds() / 60)
                    next_eta = f"约 {diff_min} 分钟后 ({next_dt.strftime('%H:%M')})"
                else:
                    next_eta = "周期已到，离席超 45s 时自动触发"
            except Exception:
                pass

        return {
            "is_enabled": self.is_enabled,
            "is_patrolling": self.is_patrolling,
            "interval_minutes": self.interval_minutes,
            "idle_threshold_seconds": self.idle_threshold_seconds,
            "current_idle_seconds": round(idle_secs, 1),
            "is_user_active": idle_secs < self.idle_threshold_seconds,
            "last_inspected_at": self.last_inspected_at or "尚未执行",
            "next_run_eta": next_eta,
            "last_status": self.last_status,
            "last_result_summary": self.last_result_summary,
            "urgent_alerts_history": self.urgent_alerts_history[:10]
        }

    def set_enabled(self, enabled: bool) -> bool:
        """开启或暂停后台守护"""
        self.is_enabled = bool(enabled)
        cfg = load_group_config()
        cfg["daemon_enabled"] = self.is_enabled
        save_group_config(cfg)
        logger.info(f"后台守护调度器已设为: {'启用' if self.is_enabled else '暂停'}")
        return self.is_enabled

    def set_interval(self, minutes: int) -> int:
        """修改巡查周期"""
        self.interval_minutes = int(minutes)
        cfg = load_group_config()
        cfg["interval_minutes"] = self.interval_minutes
        save_group_config(cfg)
        logger.info(f"巡查周期已更新为: {self.interval_minutes} 分钟")
        return self.interval_minutes

# 全局单例
daemon_scheduler = CampusDaemonScheduler()
