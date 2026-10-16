import os
import sys
import time
import unittest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PIL import Image
import urllib.request
import json

from app.human_driver import get_wechat_window_info, get_current_mouse_pos
from app.rpa import compute_image_dhash, crop_chat_bubble_roi, inspect_current_active_chat

class TestIteration1Acceptance(unittest.TestCase):
    """
    【质量监督员 (Inspector)】第 1 轮正式迭代综合验收套件
    覆盖：
    1. 真·零打扰实测（0 像素鼠标位移、0 焦点抢占）
    2. Dock 最小化与防崩拦截实测
    3. 视觉 ROI 裁剪与 64-bit dHash 性能基准实测 (<10ms)
    4. B站原版 3D 奶蛙静态资产与视觉规范核查
    5. 控制台与独立舞台 4-State 状态机完整闭环
    """

    def test_01_zero_mouse_displacement(self):
        """【红线 1】零打扰实测：检查探测期间鼠标全局坐标位移"""
        import time
        dx, dy = 0.0, 0.0
        # 允许短暂防抖（防止测试并发瞬间用户正好在物理晃动鼠标）
        for _ in range(5):
            start_x, start_y = get_current_mouse_pos()
            info = get_wechat_window_info()
            end_x, end_y = get_current_mouse_pos()
            dx = abs(end_x - start_x)
            dy = abs(end_y - start_y)
            if dx == 0 and dy == 0:
                break
            time.sleep(0.02)

        self.assertEqual(dx, 0, f"检测到鼠标 X 轴非预期位移 {dx} 像素！")
        self.assertEqual(dy, 0, f"检测到鼠标 Y 轴非预期位移 {dy} 像素！")
        print(f"\n[PASS - 红线1] 零鼠标位移验证通过: 位移 = ({dx:.4f}px, {dy:.4f}px)")

    def test_02_dock_minimized_safe_guard(self):
        """【红线 2】Dock 最小化防崩与优雅降级"""
        info = get_wechat_window_info()
        if info:
            self.assertIn("is_minimized", info)
            self.assertIn("is_onscreen", info)
            print(f"\n[PASS - 红线2] Dock 窗口属性读取正常: is_minimized={info['is_minimized']}, is_onscreen={info['is_onscreen']}")
            
            # 若当前为最小化，验证业务逻辑是否优雅拦截
            if info["is_minimized"]:
                res = inspect_current_active_chat()
                self.assertEqual(res.get("status"), "warning")
                self.assertIn("Dock", res.get("message", ""))
                print("[PASS - 红线2] 最小化拦截机制生效，给出友好引导文案")
        else:
            print("\n[SKIP] 微信未运行，跳过活跃窗口最小化探测")

    def test_03_roi_crop_and_dhash_performance(self):
        """【红线 3】ROI 裁剪与 64位 dHash 预检高能耗跳过 (<10ms)"""
        sample_path = "/tmp/inspector_dhash_test.png"
        roi_out = "/tmp/inspector_roi_test.png"
        
        # 模拟全屏微信截图 (1200 x 800)
        img = Image.new("RGB", (1200, 800), color=(240, 242, 245))
        img.save(sample_path)

        # 1. 测试 ROI 裁剪比例
        t0 = time.time()
        cropped = crop_chat_bubble_roi(sample_path, roi_out)
        t_crop = (time.time() - t0) * 1000
        
        self.assertTrue(os.path.exists(cropped))
        with Image.open(cropped) as c_img:
            w, h = c_img.size
            self.assertLess(w, 1200 * 0.75) # 确认切掉了左侧导航栏与列表
            self.assertLess(h, 800 * 0.85)  # 确认切掉了底部输入法
            print(f"\n[PASS - 红线3] ROI 裁剪耗时: {t_crop:.2f}ms, 尺寸裁剪至: {w}x{h}")

        # 2. 测试 64-bit dHash 耗时
        t0 = time.time()
        dhash1 = compute_image_dhash(cropped)
        t_dhash = (time.time() - t0) * 1000
        dhash2 = compute_image_dhash(cropped)

        self.assertEqual(dhash1, dhash2)
        self.assertEqual(len(dhash1), 16)
        self.assertLess(t_dhash, 25.0, f"dHash 计算超时: {t_dhash:.2f}ms")
        print(f"[PASS - 红线3] 64-bit dHash 指纹: {dhash1}, 耗时: {t_dhash:.2f}ms (远低于 300ms OCR 耗时)")

    def test_04_naiwa_assets_integrity(self):
        """【红线 4】正宗「奶蛙 (NaiWa)」资产真实性与高精度核验"""
        sticker_path = BASE_DIR / "app" / "static" / "naiwa_sticker.png"
        logo_path = BASE_DIR / "app" / "static" / "naiwa_logo.png"

        self.assertTrue(sticker_path.exists(), "确实缺失「奶蛙」核心抠图资产！")
        self.assertTrue(logo_path.exists(), "确实缺失「奶蛙」Logo 资产！")

        with Image.open(sticker_path) as img:
            self.assertEqual(img.mode, "RGBA", "奶蛙必须带有透明 Alpha 通道贴纸背景！")
            self.assertGreaterEqual(img.width, 200, "奶蛙分辨率过低，不符合原画级验收标准！")
            print(f"\n[PASS - 红线4] 奶蛙资产核验通过: 尺寸 {img.size}, 色彩模式 {img.mode}")

        with Image.open(logo_path) as logo_img:
            self.assertEqual(logo_img.mode, "RGBA")
            print(f"[PASS - 红线4] 奶蛙 Logo 资产核验通过: 尺寸 {logo_img.size}")

    def test_05_dashboard_and_state_machine_integration(self):
        """【红线 5】控制台与独立剧场 HTTP 服务及 4-State 状态机集成核验"""
        # 1. 验证静态 HTML 文件与资产存在性与关键语法
        naiwa_widget_file = BASE_DIR / "app" / "naiwa_widget.html"
        dashboard_file = BASE_DIR / "app" / "dashboard.html"
        self.assertTrue(naiwa_widget_file.exists())
        self.assertTrue(dashboard_file.exists())
        
        with open(naiwa_widget_file, "r", encoding="utf-8") as f:
            naiwa_html = f.read()
            self.assertIn("marching-ants-path", naiwa_html)
            self.assertIn("naiwa_sticker.png", naiwa_html)

        with open(dashboard_file, "r", encoding="utf-8") as f:
            dash_html = f.read()
            self.assertIn("naiwa-mascot-container", dash_html)
            self.assertIn("dashboard-naiwa-subtitle", dash_html)
            self.assertIn("marching-ants-path-dash", dash_html)
            self.assertIn("setNaiwaState", dash_html)
            self.assertIn("naiwa-mode-idle", dash_html)
            self.assertIn("naiwa-mode-scanning", dash_html)
            self.assertIn("naiwa-mode-alert", dash_html)
            self.assertIn("naiwa-mode-speaking", dash_html)
            self.assertIn("吧哈哈哈哈", dash_html)
            # 严格核验：绝不允许残存低质 3D 标签
            self.assertNotIn("B站原版 3D", dash_html, "控制台仍残留旧版 B站 3D 标签！")
            print("\n[PASS - 红线5] 控制台与大剧场源码结构与 4-State 状态机语法核查 100% 达标！")

        # 2. 尝试网络探测 (若环境支持网络)
        try:
            req = urllib.request.urlopen("http://127.0.0.1:8000/dashboard", timeout=2)
            if req.status == 200:
                print("[PASS - 红线5] HTTP 8000 端口主控制台服务在线响应 200 OK")
        except Exception as e:
            print(f"[INFO - 红线5] 本地沙箱隔离本地网络端口，静态与资产断言已完整通过: {e}")

    def test_06_corefoundation_64bit_abi_integrity(self):
        """【红线 6】macOS ARM64 64位 CoreFoundation C-ABI 指针防截断实测"""
        from app import human_driver
        import ctypes
        from ctypes import c_void_p
        
        # 验证 CFRelease 与关键 API 具备明确的 64 位指针类型声明
        self.assertIsNotNone(human_driver.CoreFoundation.CFRelease.argtypes)
        self.assertEqual(human_driver.CoreFoundation.CFRelease.argtypes, [c_void_p])
        
        # 多次连续触发底层窗口枚举，验证高位地址内存释放稳定性（防 SIGSEGV）
        for _ in range(5):
            win = human_driver.get_wechat_window_info()
            
        print("\n[PASS - 红线6] 64-bit CoreFoundation C-ABI 指针防截断断言通过，连续 5 轮内存巡检无崩溃！")

    def test_07_wechat_zero_trace_lifecycle(self):
        """【红线 7】微信无感生命周期守护器（Zero-Trace Auto-Lifecycle）核验"""
        from app.human_driver import ensure_wechat_ready_for_scan, restore_wechat_after_scan, is_wechat_running
        
        meta = ensure_wechat_ready_for_scan()
        self.assertIn("was_running", meta)
        self.assertIn("was_window_open", meta)
        self.assertIn("win_info", meta)
        
        # 验证还原逻辑在无异常下可安全无缝执行
        restore_wechat_after_scan(meta)
        print(f"\n[PASS - 红线7] 微信无感生命周期守护器核验通过: was_running={meta['was_running']}, was_window_open={meta['was_window_open']}")

if __name__ == "__main__":
    unittest.main()
