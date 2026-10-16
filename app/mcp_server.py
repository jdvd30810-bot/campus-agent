"""
Campus-Agent MCP (Model Context Protocol) Server
规范实现：Anthropic / Open-Source Model Context Protocol (JSON-RPC 2.0 over stdio)

允许外部通用 Agent (Claude Desktop, Cursor, Antigravity, WorkBuddy 等)
直接调用 Campus-Agent 提供的端侧视觉感知与苹果原生自动化工具。
"""

import sys
import json
import logging
from datetime import datetime
from typing import Dict, Any, List

from app.rpa import inspect_current_active_chat, execute_batch_inspection
from app.apple_sync import add_to_apple_reminders, add_to_apple_calendar, parse_datetime
from app.database import get_recent_synced_items, record_synced_item, compute_item_fingerprint
from app.groups_manager import load_group_config

# MCP 必须使用 stderr 输出日志，以免污染 stdout 中的 JSON-RPC 通信
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [MCP] [%(levelname)s] %(message)s"
)
logger = logging.getLogger("campus-agent.mcp")

TOOLS_REGISTRY = [
    {
        "name": "wechat_get_active_chat_ddls",
        "description": "零按键安全捕获 macOS 屏幕当前打开的微信聊天窗口，通过 Apple Vision 硬件加速 OCR 识别文字，并由 DeepSeek LLM 提取 DDL 待办与重要通知，支持自动同步写入苹果提醒事项与日历。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "auto_sync": {
                    "type": "boolean",
                    "description": "是否自动写入 Apple 提醒事项/日历 (默认 true)",
                    "default": True
                }
            }
        }
    },
    {
        "name": "wechat_roam_and_inspect_subscribed",
        "description": "执行拟人化无痕巡航：自动按序扫描用户在 Campus-Agent 中订阅的所有校园微信群，利用视觉高水位线跳过未更新群聊，全自动提炼 DDL 并秒速复原用户工作区现场。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_scroll_pages": {
                    "type": "integer",
                    "description": "向下滑动寻找未显示订阅群的最大翻页数 (默认 3)",
                    "default": 3
                }
            }
        }
    },
    {
        "name": "apple_sync_task",
        "description": "将指定的校园任务直接写入 Apple 官方「提醒事项 (Reminders)」或「日历 (Calendar)」，支持精细化分类（课程作业/行政通知/社团活动）并返回系统级双向验真回执。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "待办事项标题，例如：'提交操作系统大作业实验报告'"
                },
                "due_datetime": {
                    "type": "string",
                    "description": "截止或开始时间，格式：YYYY-MM-DD HH:MM:SS"
                },
                "category": {
                    "type": "string",
                    "enum": ["course", "admin", "activity"],
                    "description": "分类：course(课程作业/考试) | admin(行政问卷/评优) | activity(社团讲座/日常)",
                    "default": "course"
                },
                "notes": {
                    "type": "string",
                    "description": "详细备注说明或提交平台地点",
                    "default": ""
                },
                "is_calendar_event": {
                    "type": "boolean",
                    "description": "是否为固定时段日历活动 (True 为日历，False 为提醒事项)",
                    "default": False
                }
            },
            "required": ["title"]
        }
    },
    {
        "name": "get_campus_schedule",
        "description": "从 Campus-Agent 本地数据库中查询已成功验真记录的最新校园待办、作业 DDL 与日历日程存根。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "获取的最大条目数 (默认 20)",
                    "default": 20
                }
            }
        }
    },
    {
        "name": "list_monitored_groups",
        "description": "查询当前配置的重点关注微信群列表，包括启用状态、归属分类以及官方可信发言人白名单。",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

def handle_call_tool(tool_name: str, arguments: Dict[str, Any]) -> List[Dict[str, Any]]:
    """工具分发处理器"""
    logger.info(f"收到 MCP 工具调用: {tool_name} | 参数: {arguments}")
    
    if tool_name == "wechat_get_active_chat_ddls":
        result = inspect_current_active_chat()
        return [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
        
    elif tool_name == "wechat_roam_and_inspect_subscribed":
        pages = arguments.get("max_scroll_pages", 3)
        result = execute_batch_inspection()
        return [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
        
    elif tool_name == "apple_sync_task":
        title = arguments.get("title")
        due_str = arguments.get("due_datetime")
        category = arguments.get("category", "course")
        notes = arguments.get("notes", "")
        is_cal = arguments.get("is_calendar_event", False)
        
        dt = parse_datetime(due_str)
        if is_cal and dt:
            receipt = add_to_apple_calendar(title, dt, notes=notes)
        else:
            receipt = add_to_apple_reminders(title, due_datetime=dt, notes=notes, priority=1, category=category)
            
        if receipt:
            fp = compute_item_fingerprint(title, due_str or "", category)
            record_synced_item(
                group_name="MCP_Tool_Call",
                fingerprint=fp,
                title=title,
                due_datetime=due_str or "",
                category=category,
                apple_item_id=receipt.get("apple_id", ""),
                verified=True
            )
            return [{"type": "text", "text": json.dumps({"status": "success", "receipt": receipt}, ensure_ascii=False, indent=2)}]
        else:
            return [{"type": "text", "text": json.dumps({"status": "error", "message": "写入系统日历/提醒事项失败"}, ensure_ascii=False)}]
            
    elif tool_name == "get_campus_schedule":
        limit = arguments.get("limit", 20)
        items = get_recent_synced_items(limit=limit)
        return [{"type": "text", "text": json.dumps(items, ensure_ascii=False, indent=2)}]
        
    elif tool_name == "list_monitored_groups":
        cfg = load_group_config()
        return [{"type": "text", "text": json.dumps(cfg, ensure_ascii=False, indent=2)}]
        
    else:
        return [{"type": "text", "text": f"Error: Unknown tool {tool_name}"}]

def run_stdio_mcp_server():
    """以标准 stdio 运行 MCP JSON-RPC 2.0 服务"""
    logger.info("Campus-Agent MCP Server 已就绪，正在监听 stdin...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            logger.error(f"无法解析 JSON-RPC 请求: {e}")
            continue

        req_id = req.get("id")
        method = req.get("method")
        params = req.get("params", {})

        if method == "initialize":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "campus-agent-gateway",
                        "version": "2.1.0"
                    }
                }
            }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        elif method == "notifications/initialized":
            logger.info("客户端已完成 MCP 握手并就绪。")

        elif method == "ping":
            resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        elif method == "tools/list":
            resp = {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": TOOLS_REGISTRY
                }
            }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        elif method == "tools/call":
            tool_name = params.get("name")
            tool_args = params.get("arguments", {})
            try:
                content = handle_call_tool(tool_name, tool_args)
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": content
                    }
                }
            except Exception as tool_err:
                logger.error(f"工具执行异常: {tool_err}")
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32603,
                        "message": str(tool_err)
                    }
                }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()

        else:
            if req_id is not None:
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()

if __name__ == "__main__":
    run_stdio_mcp_server()
