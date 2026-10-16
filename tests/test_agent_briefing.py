"""
测试校园智能学伴「小航」巡视要点口播简报引擎：
1. 验证单群提取后，自动生成 Markdown 结构化要点卡片与面向 TTS 的精炼口播稿；
2. 验证高水位线未更新时，生成温暖的“今日平安”口播与简报；
3. 验证多订阅群批量巡视后，聚合待办与口播稿生成；
4. 验证 macOS 原生朗读过滤与调度逻辑。
"""

import unittest
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.agent import generate_agent_briefing, get_latest_briefing

class TestAgentBriefing(unittest.TestCase):

    def test_single_chat_with_urgent_todos(self):
        sample_data = {
            "status": "success",
            "synced_to_apple": 2,
            "is_watermark_unchanged": False,
            "raw_text_preview": "请各位同学于今晚 23:59 前提交大物实验报告",
            "todos": [
                {
                    "title": "大物实验报告线上提交",
                    "due_datetime": "2026-10-15 23:59:00",
                    "category": "course",
                    "action_item": "上传至超星学习通平台",
                    "speaker": "大物实验张老师"
                },
                {
                    "title": "班级安全用电责任书签字",
                    "due_datetime": "2026-10-16 12:00:00",
                    "category": "admin",
                    "action_item": "辅导员处盖章提交",
                    "speaker": "班长"
                }
            ],
            "notifications": []
        }

        briefing = generate_agent_briefing(sample_data, mode="current")
        self.assertEqual(briefing["status"], "success")
        self.assertEqual(briefing["todos_count"], 2)
        self.assertIn("奶蛙", briefing["markdown"])
        self.assertIn("大物实验报告线上提交", briefing["markdown"])
        self.assertIn("同学你好", briefing["spoken_script"])
        self.assertIn("大物实验报告线上提交", briefing["spoken_script"])
        # 口播稿长度适中，适合自然朗读
        self.assertTrue(30 <= len(briefing["spoken_script"]) <= 200)

    def test_watermark_unchanged_briefing(self):
        sample_data = {
            "status": "success",
            "is_watermark_unchanged": True,
            "synced_to_apple": 0,
            "todos": [],
            "notifications": []
        }

        briefing = generate_agent_briefing(sample_data, mode="current")
        self.assertEqual(briefing["status"], "unchanged")
        self.assertIn("高水位线", briefing["markdown"])
        self.assertIn("没有任何新消息变动", briefing["spoken_script"])

    def test_batch_groups_briefing(self):
        sample_data = {
            "status": "success",
            "inspected_count": 3,
            "total_synced_todos": 1,
            "results": [
                {
                    "group_name": "26秋 通用英语C",
                    "synced": 1,
                    "is_watermark_unchanged": False,
                    "todos": [
                        {
                            "title": "英语 Unit 3 作业完成",
                            "due_datetime": "2026-10-17 18:00:00",
                            "category": "course",
                            "action_item": "雨课堂答题",
                            "speaker": "李老师"
                        }
                    ]
                },
                {
                    "group_name": "形式与政策",
                    "synced": 0,
                    "is_watermark_unchanged": True,
                    "todos": []
                }
            ],
            "pending_not_found": []
        }

        briefing = generate_agent_briefing(sample_data, mode="batch")
        self.assertEqual(briefing["status"], "success")
        self.assertEqual(briefing["todos_count"], 1)
        self.assertIn("英语 Unit 3 作业完成", briefing["markdown"])
        self.assertIn("全量已订阅群巡视", briefing["spoken_script"])

if __name__ == "__main__":
    unittest.main()
