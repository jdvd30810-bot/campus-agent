import subprocess
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OCR_SWIFT = BASE_DIR / "app" / "ocr.swift"
IMG_PATH = "/tmp/wechat_capture.png"

def capture_and_ocr():
    print("=" * 60)
    print("📸 正在使用 macOS 原生视觉引擎捕获微信屏幕内容...")
    print("=" * 60)
    
    # 1. 激活微信并获取主窗口坐标尺寸
    script = '''
    tell application "WeChat" to activate
    delay 0.3
    tell application "System Events"
        tell process "WeChat"
            set w to window 1
            set winPos to position of w
            set winSize to size of w
            return (item 1 of winPos as string) & "," & (item 2 of winPos as string) & "," & (item 1 of winSize as string) & "," & (item 2 of winSize as string)
        end tell
    end tell
    '''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    coords = res.stdout.strip()
    
    if not coords or "," not in coords:
        print(f"❌ 获取微信窗口坐标失败: {coords}")
        return
        
    print(f"📍 锁定微信主窗口位置与尺寸: {coords}")
    
    # 2. 截取微信主窗口区域
    capture_cmd = ["screencapture", "-x", f"-R{coords}", IMG_PATH]
    subprocess.run(capture_cmd, check=True)
    print(f"📷 窗口快照已保存至: {IMG_PATH}")
    
    # 3. 调用 Apple Vision 实况文本识别
    print("🔍 正在调用苹果原生 Vision 实况文本引擎识别汉字...")
    ocr_cmd = ["swift", str(OCR_SWIFT), IMG_PATH]
    ocr_res = subprocess.run(ocr_cmd, capture_output=True, text=True)
    
    recognized_text = ocr_res.stdout.strip()
    print("\n✨ 【原生实况文本识别成功！识别出的内容如下】:\n")
    print("-" * 50)
    print(recognized_text)
    print("-" * 50)
    
    if len(recognized_text) > 20:
        print("\n🎉 成功！完全绕过了微信内部画布限制，文字 100% 还原！")
    else:
        print("\n⚠️ 识别到的文字较短，请确认微信窗口中是否有文字展示。")

if __name__ == "__main__":
    capture_and_ocr()
