import time
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.human_driver import (
    get_wechat_pid,
    mouse_click_pid,
    mouse_scroll_pid,
    get_current_mouse_pos,
    get_wechat_bounds
)

def test_option1_zero_displacement():
    print("=" * 70)
    print("🔬 [方案一验证] macOS CoreGraphics 定向进程私有事件注入测试")
    print("   目标: 物理硬件光标 0.00px 位移 · 零打扰后台交互 (CGEventPostToPid)")
    print("=" * 70)

    pid = get_wechat_pid()
    print(f"1. [进程探测] WeChat PID: {pid}")
    if not pid:
        print("⚠️ 未找到 WeChat 进程，测试跳过。")
        return

    bounds = get_wechat_bounds(activate=False)
    print(f"2. [窗口探测] WeChat Bounds: {bounds}")
    
    target_x = bounds["x"] + 160 if bounds else 200.0
    target_y = bounds["y"] + 200 if bounds else 300.0

    pos_before = get_current_mouse_pos()
    print(f"3. [初始光标] 真实物理硬件鼠标坐标: ({pos_before[0]:.2f}, {pos_before[1]:.2f})")

    print(f"4. [事件注入] 正在向 WeChat PID {pid} 发送定向点击事件: ({target_x}, {target_y})...")
    mouse_click_pid(target_x, target_y, pid=pid, delay_after=0.1)

    print(f"5. [滚轮注入] 正在向 WeChat PID {pid} 发送定向滚轮事件: lines=-3...")
    mouse_scroll_pid(target_x, target_y, lines=-3, pid=pid)

    pos_after = get_current_mouse_pos()
    print(f"6. [最终光标] 注入后物理硬件鼠标坐标: ({pos_after[0]:.2f}, {pos_after[1]:.2f})")

    dist = ((pos_after[0] - pos_before[0]) ** 2 + (pos_after[1] - pos_before[1]) ** 2) ** 0.5
    print(f"7. [位移评估] 物理硬件光标总位移: {dist:.4f} px")

    assert dist == 0.0, f"物理光标发生偏移: {dist}px!"
    print("\n✅ 【方案一验证成功】硬件光标位移量严格为 0.0000 px！用户日常鼠标操作不受任何抢占干扰！")

if __name__ == "__main__":
    test_option1_zero_displacement()
