import json
import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.scheduler_daemon import daemon_scheduler, CampusDaemonScheduler

class TestIteration2DaemonScheduler(unittest.TestCase):
    """
    【质量监督员 (Inspector)】第 2 轮迭代 (Feature 2) 验收测试套件：
    后台定时守护巡检机制与高危 DDL 声光预警引擎 (Daemon Scheduler & Urgent DDL Alert)
    验收范围：
    1. 守护器单例与状态机遥测完整性
    2. 物理外设空闲感知避让 (Idle-Aware Adaptive Yielding)
    3. 临近截止高危 DDL 判定器 (Urgent DDL Sieve)
    4. macOS 原生横幅通知 + Mac 硬件扬声器声光预警管道
    5. REST API 接口完整性与数据契约
    6. 控制台 Meta Muse 守护监控面板与交互组件契约核查
    """

    def setUp(self):
        self.client = TestClient(app)
        self.scheduler = daemon_scheduler

    def test_01_daemon_singleton_and_status(self):
        """【验收 1】守护调度器单例与状态机遥测完整性"""
        another_scheduler = CampusDaemonScheduler()
        self.assertIs(self.scheduler, another_scheduler, "守护器必须是全局单例！")

        status = self.scheduler.get_status()
        self.assertIsInstance(status, dict)
        self.assertIn("is_enabled", status)
        self.assertIn("is_patrolling", status)
        self.assertIn("interval_minutes", status)
        self.assertIn("idle_threshold_seconds", status)
        self.assertIn("current_idle_seconds", status)
        self.assertIn("is_user_active", status)
        self.assertIn("next_run_eta", status)
        self.assertIn("last_status", status)
        self.assertIn("urgent_alerts_history", status)

        self.assertEqual(status["idle_threshold_seconds"], 45.0, "安全空闲阈值必须严格设定为 45.0 秒！")
        print(f"\n[PASS - 验收1] 守护调度器单例与状态机遥测核验通过: 空闲阈值={status['idle_threshold_seconds']}s, 状态={status['last_status']}")

    def test_02_urgent_ddl_sieve_rules(self):
        """【验收 2】高危 DDL 智能判定引擎（24h 截止/高优/课程关键节点）"""
        now = datetime.now()

        # Case A: 12 小时后截止 -> 严格高危 🚨
        todo_12h = {
            "title": "计算机体系结构大作业",
            "due_datetime": (now + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S"),
            "category": "course",
            "priority": "NORMAL"
        }
        is_urgent, reason, hours = self.scheduler.check_is_urgent_todo(todo_12h)
        self.assertTrue(is_urgent, "12 小时内截止的待办必须判定为高危！")
        self.assertIn("临近最后截止", reason)
        self.assertAlmostEqual(hours, 12.0, delta=0.1)

        # Case B: 3 天后截止且普通优先级 -> 非高危
        todo_3d = {
            "title": "阅读第三章课文",
            "due_datetime": (now + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            "category": "course",
            "priority": "NORMAL"
        }
        is_urgent, reason, hours = self.scheduler.check_is_urgent_todo(todo_3d)
        self.assertFalse(is_urgent, "3 天后截止且非高优的事项不应判定为高危！")

        # Case C: 36 小时后截止但 priority 为 HIGH -> 判定为重点高危
        todo_high = {
            "title": "国家奖学金综测加分材料线上审核",
            "due_datetime": (now + timedelta(hours=36)).strftime("%Y-%m-%d %H:%M:%S"),
            "category": "admin",
            "priority": "HIGH"
        }
        is_urgent, reason, hours = self.scheduler.check_is_urgent_todo(todo_high)
        self.assertTrue(is_urgent, "48 小时内的 HIGH 优先级事项必须纳入高危预警！")
        self.assertIn("官方高优事项", reason)

        # Case D: 刚刚逾期 2 小时 -> 逾期补交通知
        todo_overdue = {
            "title": "形势与政策线上作业",
            "due_datetime": (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
            "category": "course",
            "priority": "NORMAL"
        }
        is_urgent, reason, hours = self.scheduler.check_is_urgent_todo(todo_overdue)
        self.assertTrue(is_urgent, "6 小时内逾期的待办应触发补交提醒！")
        self.assertIn("补交", reason)

        # Case E: 无具体截止时间 -> 优雅放行
        todo_no_time = {
            "title": "关注社团招新动态",
            "due_datetime": None,
            "category": "activity"
        }
        is_urgent, reason, hours = self.scheduler.check_is_urgent_todo(todo_no_time)
        self.assertFalse(is_urgent)

        print("\n[PASS - 验收2] 高危 DDL 判定引擎实测 100% 达标：24h 绝对拦截、48h HIGH 拦截、超期补交触发！")

    def test_03_idle_aware_adaptive_yielding(self):
        """【验收 3】物理外设空闲感知避让（用户在电脑前敲击时绝不争抢鼠标）"""
        past_time = (datetime.now() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        mock_cfg = {
            "interval_minutes": 30,
            "last_inspected_at": past_time,
            "daemon_enabled": True,
            "groups": []
        }

        # 模拟周期已到且当前用户正在敲键盘（物理空闲仅 8.5 秒 < 45 秒）
        with patch("app.scheduler_daemon.load_group_config", return_value=mock_cfg):
            with patch("app.scheduler_daemon.get_system_idle_seconds", return_value=8.5):
                res = self.scheduler.patrol_cycle(force=False)
                self.assertEqual(res["status"], "yielding", "用户活跃操作时未触发智能避让！")
                self.assertEqual(res["idle_seconds"], 8.5)
                self.assertEqual(res["threshold"], 45.0)
                self.assertIn("避让", res["message"])
                self.assertEqual(self.scheduler.last_status, "yielding")

        print("\n[PASS - 验收3] 物理空闲感知避让实测通过：用户活跃时 100% 主动挂起，绝对零打扰！")

    def test_04_urgent_alert_audio_visual_pipeline(self):
        """【验收 4】macOS 原生系统横幅通知 + Mac 物理扬声器预警发声实测"""
        # 测试一键模拟高危 DDL 预警
        res = self.scheduler.test_simulate_alert()
        self.assertEqual(res["status"], "alerted")
        self.assertIn("record", res)
        record = res["record"]
        self.assertIn("计算机系统大作业", record["title"])
        self.assertIn("临近最后截止", record["urgent_reason"])
        self.assertIn("吧哈哈哈哈", record["spoken_script"])

        # 验证审计流水记录正常追加
        history = self.scheduler.urgent_alerts_history
        self.assertTrue(len(history) > 0)
        self.assertEqual(history[0]["title"], "计算机系统大作业线上提交")

        print(f"\n[PASS - 验收4] 高危 DDL 声光双重预警管道核验通过: 记录 ID={record['id']}, 口播={record['spoken_script'][:25]}...")

    def test_05_rest_api_daemon_endpoints(self):
        """【验收 5】FastAPI 后台守护网关全套 REST API 契约与功能测试"""
        # 1. GET /api/v1/daemon/status
        resp = self.client.get("/api/v1/daemon/status")
        self.assertEqual(resp.status_code, 200)
        status_data = resp.json()
        self.assertIn("is_enabled", status_data)
        self.assertIn("current_idle_seconds", status_data)

        # 2. POST /api/v1/daemon/toggle
        resp_toggle = self.client.post("/api/v1/daemon/toggle", json={"enabled": False})
        self.assertEqual(resp_toggle.status_code, 200)
        self.assertFalse(resp_toggle.json()["is_enabled"])

        # 恢复启用
        resp_toggle2 = self.client.post("/api/v1/daemon/toggle", json={"enabled": True})
        self.assertEqual(resp_toggle2.status_code, 200)
        self.assertTrue(resp_toggle2.json()["is_enabled"])

        # 3. POST /api/v1/daemon/interval
        resp_int = self.client.post("/api/v1/daemon/interval", json={"interval_minutes": 60})
        self.assertEqual(resp_int.status_code, 200)
        self.assertEqual(resp_int.json()["interval_minutes"], 60)

        # 恢复默认 30 分钟
        self.client.post("/api/v1/daemon/interval", json={"interval_minutes": 30})

        # 4. POST /api/v1/daemon/test_alert
        resp_alert = self.client.post("/api/v1/daemon/test_alert")
        self.assertEqual(resp_alert.status_code, 200)
        self.assertEqual(resp_alert.json()["status"], "alerted")

        print("\n[PASS - 验收5] 后台守护网关全套 REST API (status/toggle/interval/test_alert) 100% 联通！")

    def test_06_dashboard_daemon_panel_contract(self):
        """【验收 6】Meta Muse 控制台守护监控面板与交互前端契约核查"""
        dash_file = BASE_DIR / "app" / "dashboard.html"
        self.assertTrue(dash_file.exists())

        with open(dash_file, "r", encoding="utf-8") as f:
            html = f.read()

        # 1. 核心 Tab 按钮与面板
        self.assertIn('id="tab-btn-daemon"', html)
        self.assertIn('id="tab-panel-daemon"', html)
        self.assertIn('id="daemonStatusBadge"', html)

        # 2. 状态卡片组件与指标表盘
        self.assertIn('id="daemonIntervalSelect"', html)
        self.assertIn('id="daemonEnableToggle"', html)
        self.assertIn('id="daemonStateTitle"', html)
        self.assertIn('id="daemonModePill"', html)
        self.assertIn('id="daemonIdleSecs"', html)
        self.assertIn('id="daemonIdleBar"', html)
        self.assertIn('id="daemonPatrolBtn"', html)
        self.assertIn('id="daemonAlertBtn"', html)
        self.assertIn('id="urgentAlertsList"', html)

        # 3. 前端交互与定时轮询脚本
        self.assertIn("loadDaemonStatus", html)
        self.assertIn("toggleDaemonState", html)
        self.assertIn("changeDaemonInterval", html)
        self.assertIn("triggerDaemonPatrolNow", html)
        self.assertIn("testDaemonUrgentAlert", html)
        self.assertIn("daemonPollTimer", html)

        print("\n[PASS - 验收6] Meta Muse 风格守护监控中心、外设空闲动态条与高危流水前端组件契约 100% 达标！")

if __name__ == "__main__":
    unittest.main()
