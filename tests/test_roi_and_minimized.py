import unittest
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PIL import Image

from app.human_driver import get_wechat_window_info
from app.rpa import compute_image_dhash, crop_chat_bubble_roi, inspect_current_active_chat

class TestRoiAndMinimized(unittest.TestCase):
    def test_01_window_info_minimized_fields(self):
        """测试窗口信息探测中是否包含 is_onscreen 与 is_minimized 字段"""
        info = get_wechat_window_info()
        if info:
            self.assertIn("is_onscreen", info)
            self.assertIn("is_minimized", info)
            self.assertEqual(info["is_onscreen"], not info["is_minimized"])
            print(f"\n[PASS] 微信窗口状态: is_onscreen={info['is_onscreen']}, is_minimized={info['is_minimized']}")
        else:
            print("\n[SKIP] 未找到微信窗口（非运行态），跳过字段断言")

    def test_02_dhash_calculation(self):
        """测试 64 位感知差分哈希 (dHash) 稳定度"""
        test_img_path = "/tmp/test_dhash_sample.png"
        img = Image.new("RGB", (800, 600), color=(73, 109, 137))
        img.save(test_img_path)

        hash1 = compute_image_dhash(test_img_path)
        hash2 = compute_image_dhash(test_img_path)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 16)
        print(f"\n[PASS] dHash 稳定性检验通过: {hash1}")

    def test_03_roi_crop(self):
        """测试聊天气泡 ROI 局部裁剪逻辑"""
        test_img_path = "/tmp/test_wechat_full.png"
        roi_target_path = "/tmp/test_wechat_roi.png"
        img = Image.new("RGB", (1400, 900), color=(255, 255, 255))
        img.save(test_img_path)

        cropped_file = crop_chat_bubble_roi(test_img_path, roi_target_path)
        self.assertTrue(os.path.exists(cropped_file))
        with Image.open(cropped_file) as c_img:
            self.assertLess(c_img.size[0], 1400)
            self.assertLess(c_img.size[1], 900)
            print(f"\n[PASS] ROI 裁剪检验通过: 原始 {img.size} -> 裁剪后 {c_img.size}")

if __name__ == "__main__":
    unittest.main()
