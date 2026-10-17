import os
import plistlib
import subprocess
import unittest
from pathlib import Path

class TestDesktopAppBundle(unittest.TestCase):
    """
    【Iteration 4 - 原生 macOS 独立桌面客户端自动化契约测试】
    验证 CampusAgent.app 独立桌面视窗、资源包完整性与 Mach-O 编译契约
    """

    @classmethod
    def setUpClass(cls):
        cls.base_dir = Path(__file__).resolve().parent.parent
        cls.app_bundle = cls.base_dir / "bin" / "CampusAgent.app"
        cls.plist_path = cls.app_bundle / "Contents" / "Info.plist"
        cls.macos_dir = cls.app_bundle / "Contents" / "MacOS"
        cls.binary_path = cls.macos_dir / "CampusAgent"
        cls.resources_dir = cls.app_bundle / "Contents" / "Resources"
        cls.icon_path = cls.resources_dir / "AppIcon.icns"
        cls.logo_path = cls.resources_dir / "naiwa_logo.png"
        cls.src_path = cls.base_dir / "src" / "desktop" / "campus_agent_app.m"
        cls.launcher_script = cls.base_dir / "run_desktop.sh"

    def test_01_app_bundle_structure_and_plist(self):
        """[验收1] 验证 CampusAgent.app 目录结构与 Info.plist 元数据规范"""
        self.assertTrue(self.app_bundle.exists(), f"App Bundle 路径不存在: {self.app_bundle}")
        self.assertTrue(self.plist_path.exists(), f"Info.plist 不存在: {self.plist_path}")

        with open(self.plist_path, "rb") as f:
            plist_data = plistlib.load(f)

        self.assertEqual(plist_data.get("CFBundleExecutable"), "CampusAgent")
        self.assertEqual(plist_data.get("CFBundleIdentifier"), "com.campus.agent.desktop")
        self.assertEqual(plist_data.get("CFBundlePackageType"), "APPL")
        self.assertEqual(plist_data.get("CFBundleIconFile"), "AppIcon")
        self.assertTrue(plist_data.get("NSHighResolutionCapable", False))
        
        ats = plist_data.get("NSAppTransportSecurity", {})
        self.assertTrue(ats.get("NSAllowsArbitraryLoads", False), "必须允许本地 HTTP 局域网传输")
        print("\n[PASS - 桌面验收1] App Bundle 结构与 Info.plist 元数据契约 100% 达标！")

    def test_02_native_macho_binary_executable(self):
        """[验收2] 验证编译产物 Mach-O 强类型二进制与可执行属性"""
        self.assertTrue(self.binary_path.exists(), f"可执行文件不存在: {self.binary_path}")
        self.assertTrue(os.access(self.binary_path, os.X_OK), "二进制文件必须具备可执行权限")

        # 使用 macOS file 命令探针校验 Mach-O 架构
        result = subprocess.run(["file", str(self.binary_path)], capture_output=True, text=True, check=True)
        self.assertIn("Mach-O 64-bit", result.stdout, "必须为 64-bit Mach-O 原生二进制架构")
        print(f"[PASS - 桌面验收2] 64 位 Mach-O 原生二进制属性核验通过: {result.stdout.strip()}")

    def test_03_assets_and_icns_integrity(self):
        """[验收3] 验证多分辨率 AppIcon.icns 与 Logo 图标资产完备性"""
        self.assertTrue(self.icon_path.exists(), f"AppIcon.icns 不存在: {self.icon_path}")
        self.assertGreater(self.icon_path.stat().st_size, 50000, "ICNS 图标文件体积异常，可能未包含高分辨率切图")

        self.assertTrue(self.logo_path.exists(), f"Logo 资产不存在: {self.logo_path}")
        self.assertGreater(self.logo_path.stat().st_size, 1000, "Logo 文件体积过小")
        print(f"[PASS - 桌面验收3] 原生 macOS 图标与多模态资产完备: ICNS 大小={self.icon_path.stat().st_size} bytes")

    def test_04_source_architecture_contract(self):
        """[验收4] 验证 Objective-C 桌面客户端源码中核心设计契约"""
        self.assertTrue(self.src_path.exists(), f"桌面客户端源码不存在: {self.src_path}")
        src_text = self.src_path.read_text(encoding="utf-8")

        # 核心契约断言
        self.assertIn("WKWebView", src_text, "必须基于现代 WebKit 引擎")
        self.assertIn("NSApplicationActivationPolicyRegular", src_text, "必须声明为常驻 Dock 栏的常规桌面应用")
        self.assertIn("NSWindowStyleMaskFullSizeContentView", src_text, "必须启用全景毛玻璃内容视图")
        self.assertIn("checkBackendHealth", src_text, "必须具备智能后端健康巡检自愈逻辑")
        self.assertIn("launchBackendProcess", src_text, "必须具备未启动时自动拉起后台服务能力")
        self.assertIn("windowShouldClose", src_text, "必须实现标准 Mac 窗口关闭后 Dock 驻留逻辑")
        print("[PASS - 桌面验收4] Objective-C Cocoa + WebKit 原生架构设计契约 100% 达标！")

    def test_05_launcher_script_and_codesign(self):
        """[验收5] 验证一键拉起脚本与系统 CodeSign 安全签名"""
        self.assertTrue(self.launcher_script.exists(), "一键拉起脚本 run_desktop.sh 不存在")
        self.assertTrue(os.access(self.launcher_script, os.X_OK), "run_desktop.sh 必须可执行")

        # 校验签名状态
        res = subprocess.run(["codesign", "-v", str(self.app_bundle)], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, f"CodeSign 签名校验失败: {res.stderr}")
        print("[PASS - 桌面验收5] run_desktop.sh 脚本与 codesign 系统级安全签名校验全部通过！")

if __name__ == "__main__":
    unittest.main()
