import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from app.main import app
from app.database import (
    init_db,
    record_synced_item,
    get_recent_synced_items,
    cleanup_expired_synced_items
)
from app.scheduler_daemon import daemon_scheduler
from app.apple_sync import cleanup_expired_apple_reminders

class TestExpiredCleanup(unittest.TestCase):
    """
    【Iteration 5 - 过期 DDL 与事项智能自动清理机制测试套件】
    验收范围：
    1. 本地 SQLite 过期事项判定、状态流转与过滤归档
    2. 守护调度器过期预警清理与巡查周期联动
    3. FastAPI /api/v1/todos/cleanup_expired REST API 契约
    4. Apple Reminders 自动标记已完成脚本健壮性
    """

    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

    def test_01_database_expired_cleanup_and_filtering(self):
        """[验收1] 本地数据库过期待办识别、归档与过滤"""
        now = datetime.now()
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        tomorrow_str = (now + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")

        # 插入一条已过期项和一条未来有效项
        record_synced_item(
            group_name="测试课程群A",
            fingerprint="test_fp_expired_001",
            title="已过期的编译原理作业",
            due_datetime=yesterday_str,
            category="course"
        )
        record_synced_item(
            group_name="测试课程群B",
            fingerprint="test_fp_active_002",
            title="未来的软件工程中期报告",
            due_datetime=tomorrow_str,
            category="course"
        )

        # 验证包含过期项时能正确标记 is_expired
        all_items = get_recent_synced_items(limit=10, include_expired=True)
        expired_found = [it for it in all_items if it["item_fingerprint"] == "test_fp_expired_001"]
        self.assertTrue(len(expired_found) > 0)
        self.assertTrue(expired_found[0]["is_expired"])

        # 执行数据库清理
        cleaned_count = cleanup_expired_synced_items(hours_threshold=0.0)
        self.assertGreaterEqual(cleaned_count, 1)

        # 默认查询（不含过期项）只应返回 active 项
        active_items = get_recent_synced_items(limit=10, include_expired=False)
        active_fps = [it["item_fingerprint"] for it in active_items]
        self.assertNotIn("test_fp_expired_001", active_fps, "已过期待办未被成功从活动列表中过滤！")
        self.assertIn("test_fp_active_002", active_fps, "未来有效待办不应被误清理！")
        print(f"\n[PASS - 过期清理验收1] SQLite 数据库过期待办状态流转与自动归档实测通过: 已清理 {cleaned_count} 条")

    def test_02_daemon_cleanup_expired_alerts(self):
        """[验收2] 守护调度器高危预警过期条目自动清理"""
        now = datetime.now()
        past_due = (now - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        future_due = (now + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S")

        # 构造预警历史
        daemon_scheduler.urgent_alerts_history = [
            {
                "id": "alert_old",
                "title": "昨天已截止的大作业",
                "due_datetime": past_due,
                "urgent_reason": "逾期",
                "spoken_script": "..."
            },
            {
                "id": "alert_fresh",
                "title": "今天下午截止的实验",
                "due_datetime": future_due,
                "urgent_reason": "仅剩4小时",
                "spoken_script": "..."
            }
        ]

        # 执行调度器全量清理
        res = daemon_scheduler.cleanup_expired_ddls()
        self.assertEqual(res["status"], "success")
        self.assertGreaterEqual(res["alerts_cleaned"], 1)

        # 验证过期预警已从历史中剔除，但未过期的依然保留
        remaining_ids = [a["id"] for a in daemon_scheduler.urgent_alerts_history]
        self.assertNotIn("alert_old", remaining_ids, "超过6小时的过期预警应当被自动清理！")
        self.assertIn("alert_fresh", remaining_ids, "未过期的紧急预警应当保留！")
        print(f"[PASS - 过期清理验收2] 守护调度器预警过期历史剔除通过: 剩余有效预警={len(daemon_scheduler.urgent_alerts_history)}")

    def test_03_rest_api_cleanup_endpoint(self):
        """[验收3] FastAPI POST /api/v1/todos/cleanup_expired 端点联通性"""
        resp = self.client.post("/api/v1/todos/cleanup_expired", params={"hours_past": 0.0})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("detail", data)
        self.assertIn("total_cleaned", data["detail"])
        print(f"[PASS - 过期清理验收3] /api/v1/todos/cleanup_expired API 响应契约通过: {data['message']}")

    def test_04_apple_reminders_cleanup_contract(self):
        """[验收4] Apple Reminders 清理脚本执行契约与异常防护"""
        count = cleanup_expired_apple_reminders(hours_past=0.0)
        self.assertIsInstance(count, int)
        self.assertGreaterEqual(count, 0)
        print(f"[PASS - 过期清理验收4] Apple Reminders 自动标记已完成脚本调用安全返回: {count} 项")

if __name__ == "__main__":
    unittest.main()
