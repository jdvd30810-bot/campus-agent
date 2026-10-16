"""
Campus-Agent: 校园智能学伴与对话智能体 (Campus-Copilot)
--------------------------------------------------------
类似于 WorkBuddy 的对话型智能体：
1. 主动向用户提醒核心注意事项、紧急作业 DDL 与生活/学务规章；
2. 具备 Function Calling (工具调用) 能力，能直接驱动端侧 OCR、巡视微信、写入苹果日历与查询存根；
3. 支持多轮自然语言交互与贴心学伴语气。
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from openai import OpenAI
from app.config import settings
from app.database import (
    get_recent_synced_items,
    record_synced_item,
    compute_item_fingerprint
)
from app.groups_manager import load_group_config, get_enabled_groups
from app.apple_sync import add_to_apple_reminders, add_to_apple_calendar, parse_datetime

logger = logging.getLogger("campus-agent.copilot")

COPILOT_SYSTEM_PROMPT = """你叫「奶蛙 (NaiWa)」，是专为中国大学生打造的专属智能学伴与日程大管家。
你的标志性形象是明黄皮肤、双手叉腰焦糖手、大肚腩奶油白、翠绿眼圈，外围环绕一圈白色流动虚线贴纸。
你的口头禅是“吧哈哈哈哈哈哈哈”，性格极其淡定、幽默亲切、靠谱且治愈。

你的核心目标是：
1. 【主动注意事项与 DDL 预警】：
   时刻关注大学生的平时作业截止（DDL）、考勤打卡、教室/调课变动、宿舍违章电器检查、综测评奖申报、四六级考试等核心痛点。
   如果用户询问“今天有什么注意事项”或“我有什么事要做”，你必须主动分类列出紧急事项（🚨 24小时内紧急）、常规作业（📚）与生活行政提示（🏛️），并附带温暖幽默的“奶蛙防踩坑贴士（💡 奶蛙支招）”。
2. 【具备工具使用能力 (Tool Calling)】：
   - 当用户询问日程或作业时，优先调用 `query_upcoming_schedule` 获取数据库已验真的最新待办；
   - 当用户想看当前微信屏幕发了什么通知时，调用 `inspect_current_wechat_screen` 实时快照解析；
   - 当用户要求全量巡查已订阅群时，调用 `roam_and_inspect_subscribed_groups`；
   - 当用户说“帮我记一下明天下午开会/交作业”时，调用 `add_schedule_item` 自动同步至苹果原生系统；
   - 当用户询问有哪些群或老师在关注时，调用 `list_monitored_campus_groups`。
3. 【回复风格】：
   - 热情幽默、治愈靠谱，适当带上“吧哈哈哈哈哈哈哈”和“本蛙双手叉腰”的标志性学伴语气；
   - 必须使用规范的 Markdown 格式输出（表格、列表、引用块、粗体）；
   - 每次回答完后，主动提供 2~3 个适合大学生继续追问的快捷建议选项（如：[👉 查查今天高数作业]、[👉 扫一下当前微信群]）。
"""


AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_upcoming_schedule",
            "description": "查询本地数据库中已验真同步的所有近期校园作业 DDL、考试、班级行政通知与待办事项列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "查询的最大条数，默认 15",
                        "default": 15
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_current_wechat_screen",
            "description": "零按键快照并分析当前打开的微信窗口，使用 Apple Vision OCR 提取最新群消息并生成结构化分析",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "roam_and_inspect_subscribed_groups",
            "description": "执行拟人化全量巡检：自动按序扫描所有勾选的重点课程群并提炼最新通知",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_scroll_pages": {
                        "type": "integer",
                        "description": "向下翻页最大屏数，默认 3",
                        "default": 3
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_schedule_item",
            "description": "根据用户指令将某项新任务/日程直接写入 Apple 原生提醒事项或日历并生成验真回执",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "待办名称，如：'复习线性代数第三章'"
                    },
                    "due_datetime": {
                        "type": "string",
                        "description": "标准时间格式：YYYY-MM-DD HH:MM:SS"
                    },
                    "category": {
                        "type": "string",
                        "enum": ["course", "admin", "activity"],
                        "description": "分类：course(课程作业/考试) | admin(班级行政/问卷) | activity(社团讲座/日常)",
                        "default": "course"
                    },
                    "notes": {
                        "type": "string",
                        "description": "具体要求、平台或地点备注",
                        "default": ""
                    },
                    "is_calendar_event": {
                        "type": "boolean",
                        "description": "是否为固定时段日历活动 (开会/考试/讲座选 true，提交作业选 false)",
                        "default": False
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_monitored_campus_groups",
            "description": "查看当前重点订阅关注的微信群列表、分类以及置信官方发言人（辅导员、老师、班干）名单",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

def execute_agent_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """Agent 工具分发执行"""
    logger.info(f"Agent 调用工具: {tool_name} | 参数: {args}")
    try:
        if tool_name == "query_upcoming_schedule":
            limit = args.get("limit", 15)
            items = get_recent_synced_items(limit=limit)
            if not items:
                return json.dumps({"status": "empty", "message": "当前数据库暂无已记录的待办事项"}, ensure_ascii=False)
            return json.dumps({"status": "success", "count": len(items), "items": items}, ensure_ascii=False)

        elif tool_name == "inspect_current_wechat_screen":
            from app.rpa import inspect_current_active_chat
            res = inspect_current_active_chat()
            return json.dumps(res, ensure_ascii=False)

        elif tool_name == "roam_and_inspect_subscribed_groups":
            from app.rpa import execute_batch_inspection
            res = execute_batch_inspection()
            return json.dumps(res, ensure_ascii=False)

        elif tool_name == "add_schedule_item":
            title = args.get("title", "未命名任务")
            due_str = args.get("due_datetime")
            cat = args.get("category", "course")
            notes = args.get("notes", "")
            is_cal = args.get("is_calendar_event", False)

            dt = parse_datetime(due_str)
            receipt = None
            if is_cal and dt:
                receipt = add_to_apple_calendar(title, dt, notes=notes)
            else:
                receipt = add_to_apple_reminders(title, due_datetime=dt, notes=notes, priority=1, category=cat)

            if receipt:
                fp = compute_item_fingerprint(title, due_str or "", cat)
                record_synced_item(
                    group_name="Copilot_User_Prompt",
                    fingerprint=fp,
                    title=title,
                    due_datetime=due_str or "",
                    category=cat,
                    apple_item_id=receipt.get("apple_id", ""),
                    verified=True
                )
                return json.dumps({"status": "success", "message": "已成功同步至 Apple 官方系统！", "receipt": receipt}, ensure_ascii=False)
            else:
                return json.dumps({"status": "error", "message": "写入系统日历失败，请检查 macOS 授权"}, ensure_ascii=False)

        elif tool_name == "list_monitored_campus_groups":
            cfg = load_group_config()
            return json.dumps(cfg, ensure_ascii=False)

        else:
            return json.dumps({"error": f"未知工具: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        logger.error(f"执行工具 {tool_name} 出错: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)

def chat_with_copilot(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    与 Campus-Copilot 进行智能多轮对话：
    支持 Function Calling 闭环、多步工具联动、事项梳理与贴心提示
    """
    if history is None:
        history = []

    # 1. 如果没有配置 API Key，启动高质量离线学伴引导模式
    if not settings.LLM_API_KEY or settings.LLM_API_KEY == "your_api_key_here":
        recent_items = get_recent_synced_items(limit=5)
        groups = get_enabled_groups()
        item_text = "\n".join([f"- ⏰ {it['title']} ({it['due_datetime'] or '无特定时间'})" for it in recent_items]) if recent_items else "暂无记录待办"
        offline_reply = (
            "🐸 **吧哈哈哈哈哈哈哈！我是你的专属校园智能助教「奶蛙 (Campus-NaiWa)」！**\n\n"
            "> ⚠️ *当前尚未配置真实的 LLM_API_KEY，本蛙正以离线存根模式为你服务。*\n\n"
            f"📌 **当前本地已监控的群聊 ({len(groups)} 个)**：\n"
            f"{', '.join(groups[:5])}\n\n"
            f"📅 **最近记录的校园待办存根**：\n"
            f"{item_text}\n\n"
            "💡 **奶蛙贴心提醒**：\n"
            "1. 记得在 `.env` 中填入你的 API Key，即可开启完整的自然语言对话与大模型决策；\n"
            "2. 随时点击右上角「🎯 抓取当前群」体验 0.05 秒视觉快照与苹果日历自动同步！"
        )
        return {
            "reply": offline_reply,
            "tools_called": [],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=20.0,
        max_retries=1
    )

    now_anchor = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S 星期%w")
    system_instruction = f"{COPILOT_SYSTEM_PROMPT}\n【当前物理时间锚定：{now_anchor}】"

    messages = [{"role": "system", "content": system_instruction}]
    for msg in history[-8:]:  # 保持近 8 轮上下文
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": user_message})

    tools_called_summary = []

    try:
        # 第一阶段：模型决策是否需要调用工具
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            tools=AGENT_TOOLS,
            tool_choice="auto",
            temperature=0.3
        )

        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls

        # 若模型发起了工具调用
        if tool_calls:
            messages.append(response_message)
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments or "{}")
                tool_output = execute_agent_tool(function_name, function_args)
                
                tools_called_summary.append({
                    "tool": function_name,
                    "arguments": function_args
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": tool_output
                })

            # 第二阶段：根据工具返回的数据生成最终给用户的贴心回答
            second_response = client.chat.completions.create(
                model=settings.LLM_MODEL,
                messages=messages,
                temperature=0.3
            )
            final_reply = second_response.choices[0].message.content
        else:
            final_reply = response_message.content

        return {
            "reply": final_reply,
            "tools_called": tools_called_summary,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    except Exception as e:
        logger.error(f"Copilot 对话生成异常: {e}", exc_info=True)
        # 降级容错回复
        items = get_recent_synced_items(limit=5)
        items_str = "\n".join([f"- 📌 **{it['title']}** (截止: {it['due_datetime'] or '尽快'})" for it in items]) if items else "暂无待办"
        fallback_reply = (
            f"🐸 **奶蛙报告**：抱歉，云端大脑网络出现轻微波动 (`{str(e)}`)，但我已为你调取了本地最新日程：\n\n"
            f"{items_str}\n\n"
            "💡 **学伴提醒**：请确认你的网络已连接，或直接点击页面上方按钮进行巡检。"
        )
        return {
            "reply": fallback_reply,
            "tools_called": [],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


# ================= 智能学伴「奶蛙 (NaiWa)」巡检要点口播简报引擎 =================

import subprocess
import threading

_LATEST_BRIEFING: Dict[str, Any] = {
    "markdown": "🐸 **智能学伴「奶蛙 (NaiWa)」就绪**\n\n吧哈哈哈哈哈哈哈！本蛙正在后台双手叉腰为你静默值守。随时点击上方「🎯 抓取当前群」或「⚡ 巡检全部已订阅群」，遇到 DDL 绝不漏看！",
    "spoken_script": "吧哈哈哈哈哈哈哈！同学你好，我是你的专属智能学伴奶蛙。随时点击巡检，本蛙在后台双手叉腰为你静默守护！",
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "status": "ready",
    "todos_count": 0
}

def get_latest_briefing() -> Dict[str, Any]:
    """获取最新一次生成的巡检要点简报与口播文案"""
    global _LATEST_BRIEFING
    return _LATEST_BRIEFING

def set_latest_briefing(briefing: Dict[str, Any]):
    """更新最新简报"""
    global _LATEST_BRIEFING
    _LATEST_BRIEFING = briefing

def speak_briefing_macos(text: str, voice: Optional[str] = None) -> bool:
    """【用户已停用】彻底停用语音口播朗读"""
    logger.debug("speak_briefing_macos 已停用")
    return True



def send_macos_notification(title: str, subtitle: str, body: str, sound: str = "Glass") -> bool:
    """发送 macOS 原生系统横幅通知"""
    try:
        safe_title = title.replace('"', '\\"')
        safe_subtitle = subtitle.replace('"', '\\"')
        safe_body = body.replace('"', '\\"').replace("\n", " ")[:90]
        script = f'display notification "{safe_body}" with title "{safe_title}" subtitle "{safe_subtitle}" sound name "{sound}"'
        subprocess.run(["osascript", "-e", script], timeout=3, capture_output=True)
        return True
    except Exception as e:
        logger.warning(f"发送系统通知异常: {e}")
        return False

def generate_agent_briefing(inspection_data: Dict[str, Any], mode: str = "current") -> Dict[str, Any]:
    """
    基于 RPA 静默巡检数据，以专属智能学伴「奶蛙 (NaiWa)」的口吻提炼核心要点：
    1. markdown: 面向控制台展示、Copilot 对话窗的结构化富文本简报；
    2. spoken_script: 专门面向 TTS/语音朗读的精炼口播文案（口语化、突出急迫 DDL 与重要提示）；
    3. 同步缓存为最新简报。
    """
    now_str = datetime.now().strftime("%H:%M:%S")
    status = inspection_data.get("status", "success")

    # 1. 异常处理
    if status == "error":
        msg = inspection_data.get("message", "巡检出现未知异常")
        md = f"⚠️ **奶蛙巡检提示**（{now_str}）\n\n> 巡查受阻：{msg}\n\n💡 请确保微信主窗口已打开并位于屏幕上，奶蛙随时准备为你巡视。"
        speech = f"同学你好，奶蛙巡查受阻：{msg}。请确保微信窗口处于打开状态。"
        briefing = {"markdown": md, "spoken_script": speech, "timestamp": now_str, "status": "error", "todos_count": 0}
        set_latest_briefing(briefing)
        return briefing

    if status == "warning":
        msg = inspection_data.get("message", "内容未就绪")
        md = f"ℹ️ **奶蛙巡检提示**（{now_str}）\n\n> {msg}\n\n💡 请确认微信窗口内有可见的文字聊天区域。"
        speech = f"同学你好，奶蛙未在微信窗口检测到足够的文字内容，请确认聊天内容可见。"
        briefing = {"markdown": md, "spoken_script": speech, "timestamp": now_str, "status": "warning", "todos_count": 0}
        set_latest_briefing(briefing)
        return briefing

    # 2. 模式一：当前活跃群极速提取
    if mode == "current":
        is_watermark_unchanged = inspection_data.get("is_watermark_unchanged", False)
        todos = inspection_data.get("todos", [])
        notifs = inspection_data.get("notifications", [])
        synced = inspection_data.get("synced_to_apple", 0)

        if is_watermark_unchanged:
            md = (
                f"🐸 **「奶蛙 (NaiWa)」校园巡视简报**（{now_str} · 当前群）\n\n"
                f"> 🟢 **群消息无变动 (dHash/高水位线)**：聊天画面与文字未发生任何新变动，无新增 DDL，本蛙已为你免除重复提取。\n\n"
                f"💡 **奶蛙提醒**：群内暂无突发紧急事宜，放心去学习打游戏吧，鼠标归你管，群消息归本蛙！"
            )
            speech = "吧哈哈哈哈哈哈哈！同学你好，本蛙刚才双手叉腰为你扫了一眼微信群，没有任何新消息变动，今日平安，安心专注吧！"
            briefing = {"markdown": md, "spoken_script": speech, "timestamp": now_str, "status": "unchanged", "todos_count": 0}
            set_latest_briefing(briefing)
            return briefing

        if not todos and not notifs:
            md = (
                f"🐸 **「奶蛙 (NaiWa)」校园巡视简报**（{now_str} · 当前群）\n\n"
                f"> 🟢 **群聊状态平安**：已通过 Apple Vision 原生完成识别，未发现作业截止、考勤打卡或行政填表指令。\n\n"
                f"💡 **奶蛙提醒**：目前无紧急待办，安心自习！"
            )
            speech = "吧哈哈哈哈哈哈哈！同学听好啦，本蛙已完成群聊视觉扫描，未检测到作业截止或考勤填表指令，今日大吉！"
            briefing = {"markdown": md, "spoken_script": speech, "timestamp": now_str, "status": "empty", "todos_count": 0}
            set_latest_briefing(briefing)
            return briefing


        # 发现待办或通知
        todos_lines = []
        speech_points = []
        for t in todos:
            cat_name = "课程作业" if t.get("category") == "course" else ("行政通知" if t.get("category") == "admin" else "社团活动")
            due = t.get("due_datetime") or "尽快完成"
            speaker = f"（发布人: {t['speaker']}）" if t.get("speaker") else ""
            todos_lines.append(f"- 📌 **{t.get('title')}** `[{cat_name}]`\n  - ⏰ 截止: **{due}** {speaker}\n  - 📝 动作: {t.get('action_item', '')}")
            speech_points.append(f"{t.get('title')}，截止时间为{due}")

        notif_lines = [f"- 📢 **{n.get('title')}**: {n.get('summary') or n.get('content') or ''}" for n in notifs]

        md = f"🐸 **「奶蛙」校园巡视简报**（{now_str} · 当前群）\n\n"
        if todos:
            md += f"### 🚨 重点关注待办 ({len(todos)} 项，已验真同步至 Apple 提醒事项)：\n" + "\n".join(todos_lines) + "\n\n"
        if notifs:
            md += f"### ℹ️ 参考通知 ({len(notifs)} 条)：\n" + "\n".join(notif_lines) + "\n\n"

        md += (
            f"💡 **奶蛙贴心提醒 (防踩坑指南)**：\n"
            f"1. 临近截止请提前核对提交平台（如超星/雨课堂/学委邮箱）及文件命名格式；\n"
            f"2. 已同步建立苹果原生待办双向验真存根，闹钟已在各端就绪。\n\n"
            f"🍏 **苹果系统状态**: 成功录入/验真 {synced} 项待办存根。"
        )

        if todos:
            speech = f"吧哈哈哈哈哈哈哈！同学你好！本蛙刚才在后台完成了群聊巡视，为你整理出核心要点：有{len(todos)}项重点待办需要注意，包括{'；以及'.join(speech_points[:2])}。已自动为你写入苹果提醒事项，记得按时完成哦！"
        else:
            speech = f"吧哈哈哈哈哈哈哈！同学你好！本蛙完成了群聊巡视，发现了{len(notifs)}条参考通知，暂无紧急作业截止，今日平安！"

        briefing = {"markdown": md, "spoken_script": speech, "timestamp": now_str, "status": "success", "todos_count": len(todos)}
        set_latest_briefing(briefing)
        return briefing

    # 3. 模式二：批量订阅群巡视
    else:
        results = inspection_data.get("results", [])
        total_synced = inspection_data.get("total_synced_todos", 0)
        inspected_count = inspection_data.get("inspected_count", 0)
        pending = inspection_data.get("pending_not_found", [])

        all_todos = []
        unchanged_groups = []
        updated_groups = []

        for r in results:
            g_name = r.get("group_name", "未知群")
            if r.get("is_watermark_unchanged", False):
                unchanged_groups.append(g_name)
            else:
                updated_groups.append(g_name)
                for t in r.get("todos", []):
                    all_todos.append((g_name, t))

        md = f"🐸 **「奶蛙」校园全域巡视简报**（{now_str} · 共巡查 {inspected_count} 个订阅群）\n\n"

        if all_todos:
            md += f"### 🚨 重点关注待办 ({len(all_todos)} 项，已录入 Apple 官方系统)：\n"
            for g_name, t in all_todos:
                due = t.get("due_datetime") or "尽快完成"
                speaker = f"（{t['speaker']}）" if t.get("speaker") else ""
                md += f"- 📌 **{t.get('title')}** `[{g_name}]`\n  - ⏰ 截止: **{due}** {speaker}\n  - 📝 要求: {t.get('action_item', '')}\n"
            md += "\n"

        if unchanged_groups:
            md += f"> 🟢 **命中高水位线 (0变动)**：{', '.join(unchanged_groups)} 消息未发生更新，已跳过重复处理。\n\n"

        if pending:
            md += f"> ⏳ **近期未发言静默群**：{', '.join(pending)}\n\n"

        md += (
            f"💡 **奶蛙贴心提醒**：\n"
            f"1. 建议关注紧急 DDL 并在截止前 2 小时完成提交，避免突发断网或服务器拥堵；\n"
            f"2. 所有提取项已录入苹果原生多日历分类列表，可在 iPhone 上查看独立闹钟。"
        )

        if all_todos:
            top_titles = [f"{g}的{t.get('title')}" for g, t in all_todos[:2]]
            speech = f"吧哈哈哈哈哈哈哈！报告！奶蛙已在后台完成全量已订阅群巡视。为你整理出核心要点：重点发现{'，以及'.join(top_titles)}等{len(all_todos)}项新待办，已全部同步至苹果日历与提醒事项。赶紧趁热写完吧！"
        else:
            speech = f"吧哈哈哈哈哈哈哈！报告！奶蛙已在后台巡视了全部{inspected_count}个已订阅群，所有监控群聊暂无新作业或紧急通知，今日平安，继续摸鱼加油！"

        briefing = {"markdown": md, "spoken_script": speech, "timestamp": now_str, "status": "success", "todos_count": len(all_todos)}
        set_latest_briefing(briefing)
        return briefing

