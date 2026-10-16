"""
Campus-Agent Iteration 3 (Feature 1) 验收测试套件：
macOS 顶部状态栏常驻小胶囊 (Menu Bar Pill & Status Companion)
验证 Objective-C Cocoa 原生源码、二进制快速自检、MenuBarManager 单例生命周期、REST API 网关与前端组件契约。
"""

import os
import subprocess
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app
from app.menubar_manager import MenuBarManager, menubar_manager, BINARY_PATH, SOURCE_PATH

client = TestClient(app)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestIteration3MenuBarPill(unittest.TestCase):
    """Iteration 3 方案 1: macOS 顶部状态栏常驻小胶囊验收测试"""

    def test_01_objc_source_and_binary_compilation(self):
        """【验收 1】原生 Objective-C Cocoa 源码与可执行程序编译核验"""
        self.assertTrue(SOURCE_PATH.exists(), f"MenuBar 源码不存在: {SOURCE_PATH}")
        src_content = SOURCE_PATH.read_text(encoding="utf-8")

        # 核心 Cocoa 符号断言
        self.assertIn("NSStatusBar", src_content)
        self.assertIn("NSStatusItem", src_content)
        self.assertIn("NSMenu", src_content)
        self.assertIn("NSApplicationActivationPolicyAccessory", src_content)
        self.assertIn("--test-compile", src_content)

        # 触发编译并检验二进制存在
        compiled = menubar_manager.ensure_compiled(force=True)
        self.assertTrue(compiled, "MenuBar 编译失败！")
        self.assertTrue(BINARY_PATH.exists(), f"编译后的二进制不存在: {BINARY_PATH}")

        # 运行 --test-compile 快速无头校验
        res = subprocess.run([str(BINARY_PATH), "--test-compile"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"二进制自检失败: {res.stderr}")
        self.assertIn("NaiWa MenuBar Binary OK", res.stdout)
        print("\n[PASS - 验收1] 原生 Objective-C Cocoa 编译与快速自检通过: NaiWa MenuBar Binary OK")

    def test_02_menubar_manager_singleton_lifecycle(self):
        """【验收 2】MenuBarManager 单例接口与生命周期状态核验"""
        manager = MenuBarManager.get_instance()
        self.assertIs(manager, menubar_manager)

        status = manager.get_status()
        self.assertIn("running", status)
        self.assertIn("pid", status)
        self.assertIn("binary_path", status)
        self.assertIn("binary_exists", status)
        self.assertTrue(status["binary_exists"])

        # 验证 stop 安全幂等性
        stop_res = manager.stop()
        self.assertTrue(stop_res["success"])
        self.assertFalse(manager.is_running())
        print("[PASS - 验收2] MenuBarManager 单例接口与状态生命周期安全契约达标！")

    def test_03_menubar_rest_api_gateway(self):
        """【验收 3】后台网关 MenuBar REST API 全链路核验 (/status, /start, /stop)"""
        # 1. 查询状态
        res_status = client.get("/api/v1/menubar/status")
        self.assertEqual(res_status.status_code, 200)
        data = res_status.json()
        self.assertIn("running", data)
        self.assertIn("binary_exists", data)

        # 2. 停止接口幂等性
        res_stop = client.post("/api/v1/menubar/stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertTrue(res_stop.json()["success"])

        # 3. 启动接口测试
        res_start = client.post("/api/v1/menubar/start")
        self.assertEqual(res_start.status_code, 200)
        start_data = res_start.json()
        self.assertTrue(start_data["success"])
        self.assertTrue(start_data["running"])

        # 启动后再次验证状态接口
        res_status_after = client.get("/api/v1/menubar/status")
        self.assertEqual(res_status_after.status_code, 200)
        self.assertTrue(res_status_after.json()["running"])

        # 清理停止
        client.post("/api/v1/menubar/stop")
        print("[PASS - 验收3] 后台网关 MenuBar 全套 REST API (status/start/stop) 100% 联通！")

    def test_04_menu_items_and_actions_contract(self):
        """【验收 4】状态栏胶囊下拉菜单项与高危 DDL 预警交互契约核验"""
        src_content = SOURCE_PATH.read_text(encoding="utf-8")

        # 6 大核心下拉快捷指令断言
        self.assertIn("⚡ 立即执行一次微信群巡检", src_content)
        self.assertIn("🤖 守护巡检:", src_content)
        self.assertIn("🚨 模拟高危 DDL 声光预警", src_content)
        self.assertIn("🖥️ 打开控制台 (Meta Muse)", src_content)
        self.assertIn("🐾 打开奶蛙活体桌宠大剧场", src_content)
        self.assertIn("❌ 退出状态栏常驻", src_content)

        # 遥测端点与高危 DDL 告警格式化断言
        self.assertIn("/api/v1/daemon/status", src_content)
        self.assertIn("/api/v1/daemon/trigger", src_content)
        self.assertIn("/api/v1/daemon/toggle", src_content)
        self.assertIn("/api/v1/daemon/test_alert", src_content)
        self.assertIn("hoursLeft <= 24.0", src_content)
        self.assertIn("🚨 高危待办:", src_content)
        print("[PASS - 验收4] 下拉菜单 6 大指令集与高危 DDL 遥测联动契约 100% 达标！")

    def test_05_dashboard_frontend_menubar_integration(self):
        """【验收 5】Meta Muse 控制台前端状态卡片、快捷药丸与脚本契约核验"""
        dashboard_path = PROJECT_ROOT / "app" / "dashboard.html"
        self.assertTrue(dashboard_path.exists())
        html = dashboard_path.read_text(encoding="utf-8")

        # DOM 元素核查
        self.assertIn("headerMenuBarBtn", html, "顶栏菜单栏常驻快捷按钮缺失")
        self.assertIn("menuBarStatusPill", html, "状态卡片 4 status pill 缺失")
        self.assertIn("menuBarStateTitle", html, "状态卡片 4 title 缺失")
        self.assertIn("startMenuBarBtn", html, "启动胶囊按钮缺失")
        self.assertIn("stopMenuBarBtn", html, "停止胶囊按钮缺失")

        # JS 核心逻辑核查
        self.assertIn("loadMenuBarStatus", html)
        self.assertIn("startMenuBarApp", html)
        self.assertIn("stopMenuBarApp", html)
        self.assertIn("toggleMenuBarFromHeader", html)
        self.assertIn("/api/v1/menubar/status", html)
        self.assertIn("/api/v1/menubar/start", html)
        self.assertIn("/api/v1/menubar/stop", html)
        print("[PASS - 验收5] 控制台 Meta Muse 状态卡片 4、顶栏微控制器与 JS 脚本契约 100% 达标！")


if __name__ == "__main__":
    unittest.main()
