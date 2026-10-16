import time
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.human_driver import (
    mouse_click,
    mouse_scroll,
    get_wechat_bounds,
    get_frontmost_app,
    restore_frontmost_app
)

def test_human_like_sidebar():
    print("=" * 65)
    print("👤 Campus-Agent 拟人化会话栏巡视测试 (Human-Like Sidebar Roaming)")
    print("   特性: 纯鼠标模拟 / 绝对 0 键盘按键 / 100% 杜绝误发消息 / 自动复原现场")
    print("=" * 65)
    
    # 1. 记忆现场：记录用户当前正在使用的应用（例如 VS Code、终端、Chrome）
    prev_app = get_frontmost_app()
    print(f"1. [现场记忆] 记录用户当前活跃应用: 【{prev_app or '未知/终端'}】")
    
    # 2. 锁定微信窗口
    print("2. [窗口锁定] 正在探测并唤醒微信主界面...")
    bounds = get_wechat_bounds(activate=True)
    if not bounds:
        print("\n❌ 未能锁定微信主窗口！可能原因：")
        print("   ① 微信完全未启动 (请先启动微信)")
        print("   ② 当前终端或 Python 未获得 macOS「辅助功能」权限")
        print("      (设置 -> 隐私与安全性 -> 辅助功能 -> 允许当前终端/IDE)")
        return
        
    print(f"   ✅ 微信窗口已锁定: X={bounds['x']}, Y={bounds['y']}, 宽={bounds['w']}, 高={bounds['h']}")
    
    # 3. 几何坐标解析 (基于微信 Mac 4.x 标准版式)
    # 左侧导航图标栏宽度约 60px，会话列表宽度约 250px
    # 会话列表水平中心: bounds['x'] + 180
    list_x = bounds["x"] + 180
    # 顶部搜索栏约占 65px，第一个会话行中心约在 95px
    start_y = bounds["y"] + 95
    row_height = 65
    
    print("\n3. [拟人巡视] 开始模拟人类在左侧会话栏点击前 3 个聊天：")
    for i in range(3):
        item_y = start_y + (i * row_height)
        print(f"   👉 [{i+1}/3] 鼠标轻触第 {i+1} 个群聊 (X={list_x}, Y={item_y})...")
        mouse_click(list_x, item_y, delay_after=0.1)
        time.sleep(1.0) # 模拟人眼看一眼聊天界面 (未来在此处执行 0.05秒 Vision OCR)
        
    # 4. 模拟向下滚动浏览更多群
    scroll_pos_y = start_y + 120
    print(f"\n4. [拟人滑动] 鼠标悬停至会话列表区 (X={list_x}, Y={scroll_pos_y}) 并向下滚动...")
    mouse_scroll(list_x, scroll_pos_y, lines=-5)
    time.sleep(1.2)
    
    # 5. 模拟向上滚回顶部
    print(f"5. [复位回顶] 向上滚回顶部置顶群...")
    mouse_scroll(list_x, scroll_pos_y, lines=5)
    time.sleep(0.8)
    
    # 6. 瞬间复原用户现场 (Ghost Switch)
    print(f"\n6. [现场复原] 巡视完毕，正在将屏幕无感切回: 【{prev_app}】...")
    restore_frontmost_app(prev_app)
    
    print("\n🎉 测试成功完成！全流程纯鼠标操作，未向键盘发送任何字符，绝无误触可能！")

if __name__ == "__main__":
    test_human_like_sidebar()
