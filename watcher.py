#!/usr/bin/env python3
"""
Campus-Agent - Mac 剪贴板静默守卫 (watcher.py)
-----------------------------------------------
功能：
在 Mac 后台监听剪贴板。当你在微信或任何地方按 Cmd+C 复制一段群聊通知时，
守卫自动调用本地 FastAPI 接口，经 AI 大脑提炼后，在 Mac 屏幕右上角弹出系统通知！
无需切换任何窗口。
"""

import time
import subprocess
import json
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8000/api/v1/extract"
TOKEN = "USER-888"

# 消息特征关键词（过滤掉平时复制代码、单字搜索等无关复制）
TRIGGER_KEYWORDS = [
    "通知", "作业", "截止", "ddl", "DDL", "收到", "请大家", "所有人",
    "同学们", "考试", "实验", "问卷", "提交", "链接", "教室", "开会",
    "讲座", "班级", "辅导员", "老师", "打卡"
]

def get_mac_clipboard() -> str:
    """使用 macOS 原生命令 pbpaste 读取剪贴板内容"""
    try:
        result = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception:
        return ""

def show_mac_notification(title: str, subtitle: str, message: str):
    """使用 macOS 原生 osascript 弹出系统通知横幅"""
    # 替换转义字符防止脚本报错
    safe_msg = message.replace('"', '\\"').replace("'", "’")[:120]
    safe_title = title.replace('"', '\\"')
    safe_sub = subtitle.replace('"', '\\"')
    
    script = f'display notification "{safe_msg}" with title "{safe_title}" subtitle "{safe_sub}" sound name "Glass"'
    subprocess.run(["osascript", "-e", script])

def is_campus_message(text: str) -> bool:
    """粗筛：判断复制的内容是否可能是群聊消息或通知"""
    clean_text = text.strip()
    if len(clean_text) < 4:
        return False
    # 1. 命中校园核心待办词（如：作业、通知、截止、考试、开会），长度 >= 4 即可触发 (如 '明天开会', '周五交作业')
    has_keyword = any(kw.lower() in clean_text.lower() for kw in TRIGGER_KEYWORDS)
    if has_keyword and len(clean_text) >= 4:
        return True
    # 2. 多行聊天记录或带发言人冒号的对话，长度 >= 20
    is_chat_log = ("\n" in clean_text or ":" in clean_text or "：" in clean_text) and len(clean_text) >= 20
    return is_chat_log



def send_to_api(content: str) -> dict:
    """发送给本地 FastAPI 服务处理，如果服务未启动则在进程内直调"""
    payload = {
        "token": TOKEN,
        "content": content,
        "source": "mac_clipboard"
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        # 降级：直接在进程内调用核心处理逻辑
        try:
            from app.schemas import ExtractRequest
            from app.main import process_message
            req_obj = ExtractRequest(**payload)
            res = process_message(req_obj)
            return res.dict()
        except Exception as inner_err:
            print(f"❌ 进程内处理异常: {inner_err}")
            return {}


def main():
    print("=" * 60)
    print("🚀 Campus-Agent Mac 剪贴板静默守卫已启动！")
    print(f"📡 监听接口: {API_URL}")
    print(f"🔑 当前用户 Token: {TOKEN}")
    print("💡 使用方式：在微信选中群消息按 Cmd+C，守卫会自动在后台处理并弹窗。")
    print("=" * 60)

    last_text = get_mac_clipboard()

    while True:
        try:
            current_text = get_mac_clipboard()
            
            # 检测剪贴板是否产生新内容
            if current_text and current_text != last_text:
                last_text = current_text
                
                # 检查是否符合群消息特征
                if is_campus_message(current_text):
                    print(f"\n📋 [检测到群聊/通知复制] 长度: {len(current_text)} 字符")
                    print(f"🔍 预览: {current_text[:45]}...")
                    print("🧠 正在请求 AI 大脑分析...")
                    
                    res = send_to_api(current_text)
                    if res:
                        has_items = res.get("has_actionable_items", False)
                        todos = res.get("todos", [])
                        notifications = res.get("notifications", [])
                        
                        if has_items:
                            print("✨ 提炼成功！发现待办/重要通知：")
                            print(res.get("formatted_markdown", ""))
                            
                            # 弹出 Mac 原生通知
                            summary_text = ""
                            if todos:
                                summary_text = f"已自动加入提醒: {todos[0].get('title')} ({todos[0].get('deadline', '尽快')})"
                            elif notifications:
                                summary_text = f"通知: {notifications[0].get('title')}"
                                
                            show_mac_notification(
                                title="Campus-Agent 待办提炼 (已写入Apple提醒)",
                                subtitle=f"发现 {len(todos)} 项待办，{len(notifications)} 条通知",
                                message=summary_text
                            )
                        else:
                            print("🟢 经分析该内容为闲聊或无实质待办，已忽略。")
                else:
                    # 不符合特征的普通复制，静默跳过
                    pass
            
            time.sleep(1.2)  # 每 1.2 秒检查一次剪贴板，功耗极低
            
        except KeyboardInterrupt:
            print("\n👋 剪贴板守卫已安全停止。")
            break
        except Exception as e:
            print(f"⚠️ 监听循环异常: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
