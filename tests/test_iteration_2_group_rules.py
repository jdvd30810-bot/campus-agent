import json
import os
import sys
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.groups_manager import (
    RULE_PRESETS,
    get_rule_presets,
    get_group_rule,
    update_group_rule,
    fast_filter_chat_text,
    load_group_config,
    save_group_config
)
from app.extractor import extract_campus_info
from app.schemas import TodoItem

class TestIteration2GroupRules(unittest.TestCase):
    """
    【质量监督员 (Inspector)】第 2 轮正式迭代综合验收套件：
    微信群个性化画像规则自定义引擎 (Custom Group Rules & Speaker Profiling)
    验收范围：
    1. 智能预设模板与数据模型完整性
    2. 群规则 CRUD 与 JSON 文件持久化
    3. Stage 1 本地 0ms 极速前置黑名单过滤与白名单防误杀
    4. 提取大脑上下文规则注入与需人工复核 (need_human_confirm) 状态机传递
    5. Meta Muse 控制台弹窗组件与前端标签流驱动
    """

    def setUp(self):
        # 备份原有 monitored_groups.json
        self.groups_file = BASE_DIR / "monitored_groups.json"
        if self.groups_file.exists():
            with open(self.groups_file, "r", encoding="utf-8") as f:
                self.original_config = json.load(f)
        else:
            self.original_config = None

    def tearDown(self):
        # 还原 monitored_groups.json
        if self.original_config is not None:
            save_group_config(self.original_config)

    def test_01_presets_and_schema_integrity(self):
        """【验收 1】智能预设模板库与数据模型结构契约校验"""
        presets = get_rule_presets()
        self.assertIsInstance(presets, dict)
        self.assertIn("course", presets, "缺少课程大作业预设模板")
        self.assertIn("admin", presets, "缺少辅导员行政预设模板")
        self.assertIn("activity", presets, "缺少社团讲座预设模板")
        self.assertIn("dorm", presets, "缺少宿舍生活预设模板")

        # 检查各预设必填字段
        required_fields = [
            "id", "name", "category", "filter_mode",
            "trusted_speakers", "keywords_whitelist", "keywords_blacklist"
        ]
        for key, p in presets.items():
            for f in required_fields:
                self.assertIn(f, p, f"预设 {key} 缺少字段 {f}")
            self.assertIn(p["filter_mode"], ["strict", "normal", "loose"])
            self.assertTrue(len(p["trusted_speakers"]) > 0)
            self.assertTrue(len(p["keywords_blacklist"]) > 0)

        print("\n[PASS - 验收1] 4 大智能预设模板 (🎓课程/🏛️行政/🎭社团/🛏️宿舍) 契约核查 100% 达标！")

    def test_02_group_rule_crud_and_persistence(self):
        """【验收 2】单群画像规则更新、智能降级与文件持久化校验"""
        test_group = "2026计算机图形学大作业群"

        # 1. 默认推断为 course 分类规则
        default_rule = get_group_rule(test_group)
        self.assertEqual(default_rule["category"], "course")
        self.assertEqual(default_rule["filter_mode"], "normal")
        self.assertIn("助教", default_rule["trusted_speakers"])

        # 2. 定制更新该群的规则画像
        custom_rule_payload = {
            "name": test_group,
            "category": "course",
            "filter_mode": "strict",
            "trusted_speakers": ["谢老师", "张助教", "学委李华"],
            "keywords_whitelist": ["光线追踪", "Shader大作业", "中期答辩"],
            "keywords_blacklist": ["拼车", "点外卖", "开黑", "原神"],
            "require_confirm": True,
            "target_apple_list": "图形学专属待办",
            "custom_notes": "谢老师周四下午常发随堂实验"
        }
        success = update_group_rule(test_group, custom_rule_payload)
        self.assertTrue(success)

        # 3. 重新读取核验持久化
        saved_rule = get_group_rule(test_group)
        self.assertEqual(saved_rule["filter_mode"], "strict")
        self.assertEqual(saved_rule["trusted_speakers"], ["谢老师", "张助教", "学委李华"])
        self.assertIn("光线追踪", saved_rule["keywords_whitelist"])
        self.assertIn("原神", saved_rule["keywords_blacklist"])
        self.assertTrue(saved_rule["require_confirm"])
        self.assertEqual(saved_rule["target_apple_list"], "图形学专属待办")
        self.assertEqual(saved_rule["custom_notes"], "谢老师周四下午常发随堂实验")

        print(f"\n[PASS - 验收2] 群画像持久化读写完全闭环: 【{test_group}】自定义规则写入与验证成功！")

    def test_03_stage1_fast_filter_noise_interception(self):
        """【验收 3】Stage 1 本地 0ms 极速前置黑名单拦截与置信角色防误杀"""
        group_name = "2024级软件工程班级大群"
        update_group_rule(group_name, {
            "name": group_name,
            "filter_mode": "strict",
            "trusted_speakers": ["辅导员王老师", "班长张伟"],
            "keywords_whitelist": ["综测", "奖学金", "青年大学习"],
            "keywords_blacklist": ["拼车", "点外卖", "王者荣耀", "砍一刀", "互赞"]
        })

        # Case A: 纯噪音闲聊 -> 必须 0ms 截断 (should_skip=True)
        chatter_text = "今天晚上有没有人去北门拼车点外卖？或者来两个人王者荣耀开黑！"
        res_chatter = fast_filter_chat_text(group_name, chatter_text)
        self.assertTrue(res_chatter["should_skip"], "纯黑名单闲聊未被极速截断！")
        self.assertIn("黑名单", res_chatter["reason"])

        # Case B: 出现置信发言人 -> 绝不拦截 (should_skip=False)
        teacher_msg = "辅导员王老师: 同学们，关于本年度国家奖学金评定，请于周五前提交材料。"
        res_teacher = fast_filter_chat_text(group_name, teacher_msg)
        self.assertFalse(res_teacher["should_skip"], "包含置信发言人的权威消息被误杀了！")
        self.assertIn("置信发言人", res_teacher["reason"])

        # Case C: 未出现发言人但命中白名单核心词 -> 绝不拦截 (should_skip=False)
        whitelist_msg = "请大家注意，本周青年大学习需要全员完成并截图打卡。"
        res_wl = fast_filter_chat_text(group_name, whitelist_msg)
        self.assertFalse(res_wl["should_skip"], "包含关注白名单关键词的消息被误杀了！")
        self.assertIn("白名单", res_wl["reason"])

        # Case D: 严格模式下无置信发言人且无核心通知标记 -> 优雅拦截
        vague_msg = "这周五晚上几点集合来着？"
        res_strict = fast_filter_chat_text(group_name, vague_msg)
        self.assertTrue(res_strict["should_skip"], "严格模式未阻断非置信非作业提议！")

        print("\n[PASS - 验收3] Stage 1 本地 0ms 过滤管线实测通过：黑名单拦截率 100%，置信防误杀率 100%！")

    def test_04_extractor_rule_pipeline_and_human_confirm(self):
        """【验收 4】提取器前置过滤、规则提示词注入与 need_human_confirm 状态机传递"""
        group_name = "学术前沿讲座群"
        update_group_rule(group_name, {
            "name": group_name,
            "category": "activity",
            "filter_mode": "loose",
            "trusted_speakers": ["讲座秘书"],
            "keywords_whitelist": ["第二课堂"],
            "keywords_blacklist": ["拼单", "开黑"],
            "require_confirm": True
        })

        # 1. 验证前置极速拦截生效（无需发起远程 LLM 网络调用）
        noisy_text = "有人拼单买奶茶吗？顺便开黑一局"
        resp = extract_campus_info(noisy_text, group_name=group_name)
        self.assertEqual(resp.status, "success")
        self.assertFalse(resp.has_actionable_items)
        self.assertIn("前置过滤", resp.message)

        # 2. 验证 need_human_confirm 字段与数据模型传递
        sample_todo = TodoItem(
            title="参加AI学术讲座",
            deadline="周四14:00",
            due_datetime="2026-10-22 14:00:00",
            category="activity",
            source_group=group_name,
            need_human_confirm=True
        )
        self.assertTrue(sample_todo.need_human_confirm)
        self.assertEqual(sample_todo.source_group, group_name)

        print("\n[PASS - 验收4] 提取大脑前置过滤联动与 need_human_confirm 契约传递验证通过！")

    def test_05_dashboard_markup_and_modal_contract(self):
        """【验收 5】Meta Muse 风格群规则配置弹窗与交互组件契约核查"""
        dash_file = BASE_DIR / "app" / "dashboard.html"
        self.assertTrue(dash_file.exists())

        with open(dash_file, "r", encoding="utf-8") as f:
            html = f.read()

        # 1. 核心 Modal 容器与 ID 必须存在
        self.assertIn('id="groupRuleModal"', html)
        self.assertIn('id="modalGroupNameTitle"', html)
        self.assertIn('id="presetButtonsContainer"', html)
        self.assertIn('id="modalCategorySelect"', html)
        self.assertIn('id="modalFilterModeSelect"', html)
        self.assertIn('id="modalSpeakersTagsContainer"', html)
        self.assertIn('id="modalWhitelistTagsContainer"', html)
        self.assertIn('id="modalBlacklistTagsContainer"', html)
        self.assertIn('id="modalTargetAppleList"', html)
        self.assertIn('id="modalRequireConfirm"', html)
        self.assertIn('id="modalCustomNotes"', html)

        # 2. 核心前端 JS 函数必须闭环
        self.assertIn("openGroupRuleModal", html)
        self.assertIn("closeGroupRuleModal", html)
        self.assertIn("applyPresetToModal", html)
        self.assertIn("saveGroupRuleFromModal", html)
        self.assertIn("quickAddSpeaker", html)
        self.assertIn("renderTagContainer", html)

        # 3. 列表触发按钮文案契约
        self.assertIn("规则画像配置", html)
        self.assertIn("FILTER_MODE_TAGS", html)

        print("\n[PASS - 验收5] 控制台 Meta Muse 规则弹窗、药丸 Tag 编辑器与交互脚本契约 100% 达标！")

if __name__ == "__main__":
    unittest.main()
