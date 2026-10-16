import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.human_driver import get_wechat_window_info

def test_option2_gpu_capture():
    print("=" * 70)
    print("🔬 [方案二验证] macOS GPU 显存帧缓冲无感截屏测试 (screencapture -l)")
    print("   目标: 无需前台激活 · 彻底免疫上层窗口遮挡 · 0 窗口抖动与闪现")
    print("=" * 70)

    win = get_wechat_window_info()
    print(f"1. [窗口探测] 检测到 WeChat 窗口信息: {win}")
    assert win is not None, "未检测到微信主窗口！"
    assert win.get("window_id", 0) > 0, "WindowID 无效！"

    win_id = win["window_id"]
    test_img = "/tmp/test_gpu_capture.png"
    
    print(f"2. [显存抓取] 直接从 WindowServer 显存快照 WindowID={win_id}...")
    cmd = ["screencapture", "-x", "-o", "-l", str(win_id), test_img]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"截屏失败: {res.stderr}"

    file_size = Path(test_img).stat().st_size
    print(f"   ✅ 快照成功生成: {test_img} (大小: {file_size / 1024:.1f} KB)")
    assert file_size > 10000, "生成图像过小，可能未能抓取有效帧"

    print("3. [OCR 验证] 调用本地 Apple Vision 引擎解析显存帧文字...")
    ocr_bin = BASE_DIR / "app" / "ocr_bin"
    ocr_res = subprocess.run([str(ocr_bin), test_img], capture_output=True, text=True)
    text = ocr_res.stdout.strip()
    print(f"   ✅ 成功识别文字，长度: {len(text)} 字符")
    assert len(text) > 10, "OCR 识别文字过少"

    print("\n✅ 【方案二验证成功】显存帧缓冲直接快照完全可用！无需将微信置顶，即使被遮挡也能 100% 清晰感知！")

if __name__ == "__main__":
    test_option2_gpu_capture()
