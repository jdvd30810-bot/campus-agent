import sys
import json
import urllib.request
import urllib.error
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


API_URL = "http://127.0.0.1:8000/api/v1/extract"
TOKEN = "USER-888"

# 模拟一段典型的中国大学被刷屏的群聊记录
SAMPLE_CHAT = """
辅导员-张老师: @所有人 同学们，关于本学期《大学计算机基础》期末大作业的通知：
请各位同学在本周五（10月17日）下午17:00前，将实验报告与源码打包提交到课程平台（雨课堂）。
逾期系统将自动关闭提交通道，无补交机会！
另外提醒：周四下午14:30在敏学楼B302举行创新创业讲座，参会的同学可加 0.5 综测分。
李同学: 收到
王同学: 收到
张同学: 收到+1
刘同学: [动画表情]
陈同学: 收到
赵同学: 收到收到
周同学: 谢谢老师！
"""

def test_extract():
    print("=" * 60)
    print("🧪 正在测试 Campus-Agent 核心提取接口...")
    print("=" * 60)
    
    payload = {
        "token": TOKEN,
        "content": SAMPLE_CHAT,
        "source": "unit_test"
    }
    
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        # 降级通过 FastAPI TestClient 纯内存测试
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        res = client.post("/api/v1/extract", json=payload)
        data = res.json()

    print("✅ 接口调用成功！返回结果如下：\n")
    print("【格式化展示 (快捷指令/通知用)】:")
    print(data.get("formatted_markdown"))
    print("\n【结构化待办列表】:")
    for idx, todo in enumerate(data.get("todos", []), 1):
        target_type = "📅 日历日程" if todo.get("is_calendar_event") else "⏰ 提醒事项"
        print(f"  {idx}. [{todo.get('priority')}] [{todo.get('category')}] {todo.get('title')}")
        print(f"     原始描述: {todo.get('deadline')} | 地点: {todo.get('location')} | 发言人: {todo.get('speaker')}")
        print(f"     已推算标准时间: {todo.get('due_datetime')} -> 写入目标: {target_type}")
    print("\n【重要通知列表】:")
    for idx, notice in enumerate(data.get("notifications", []), 1):
        print(f"  {idx}. {notice.get('title')}: {notice.get('summary')}")
    print("\n💡 提示：打开你的 Mac 官方「提醒事项」或「日历」App，查看是否已经自动生成了带闹钟的分类日程！")

if __name__ == "__main__":
    test_extract()

