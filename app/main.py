import asyncio
import logging
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.schemas import ExtractRequest, ExtractResponse
from app.database import init_db, verify_token, log_request
from app.extractor import extract_campus_info
from app.human_driver import get_system_idle_seconds
from app.groups_manager import (
    load_group_config, save_group_config,
    get_rule_presets, get_group_rule, update_group_rule
)
from app.rpa import execute_batch_inspection, inspect_current_active_chat

# 配置控制台日志格式，让终端打印的信息一目了然
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("campus-agent.main")

DASHBOARD_FILE = Path(__file__).resolve().parent / "dashboard.html"
NAIWA_WIDGET_FILE = Path(__file__).resolve().parent / "naiwa_widget.html"


async def background_scheduler_worker():
    """
    FastAPI 内嵌轻量级智能定时巡检守护协程：
    委托给 app.scheduler_daemon.daemon_scheduler 统一调度管理，
    结合空闲避让（>45s）、周期到期判定、高危 DDL 声光双重预警（系统横幅+硬件扬声器）。
    """
    from app.scheduler_daemon import daemon_scheduler
    logger.info("🤖 [内嵌智能守护调度器] 已启动定时自动巡检协程...")
    while True:
        try:
            await asyncio.sleep(15)  # 每 15 秒轮询一次时间与空闲状态
            # 放到后台子线程执行一轮巡查周期判定，不阻塞 FastAPI 主事件循环
            await asyncio.to_thread(daemon_scheduler.patrol_cycle, force=False)
        except asyncio.CancelledError:
            logger.info("内嵌守护调度器协程已安全退出。")
            break
        except Exception as err:
            logger.warning(f"内嵌定时调度器运行异常: {err}")
            await asyncio.sleep(10)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 服务启动时初始化数据库与定时巡检任务
    logger.info("Campus-Agent 网关正在启动...")
    init_db()
    scheduler_task = asyncio.create_task(background_scheduler_worker())
    yield
    logger.info("Campus-Agent 网关正在关闭...")
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Campus-Agent 网关服务",
    description="校园消息聚合与待办提取助手 (MVP 双轨制网关)",
    version="0.1.0",
    lifespan=lifespan
)


# 允许跨域（方便本地测试或前端调用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.staticfiles import StaticFiles
STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def health_check():
    """探针接口：检查服务是否在线"""
    logger.info("收到心跳检查 (Ping)")
    return {
        "status": "online",
        "service": "Campus-Agent Gateway",
        "supported_channels": ["mac_clipboard", "ios_shortcut"]
    }

@app.post("/api/v1/extract", response_model=ExtractResponse)
def process_message(payload: ExtractRequest):
    """
    统一消息提取接口：
    无论来自 Mac 剪贴板静默守卫，还是来自 iPhone 快捷指令，均调用此接口。
    """
    logger.info(f"收到提取请求 | 来源: {payload.source} | Token: {payload.token}")

    # 1. 简易鉴权：校验 Token
    if not verify_token(payload.token):
        logger.warning(f"鉴权失败：无效的 Token [{payload.token}]")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"无效或未授权的 Token: {payload.token}"
        )

    # 2. 检查内容是否为空
    raw_text = payload.content.strip()
    if not raw_text:
        return ExtractResponse(
            status="error",
            message="提交的聊天文本为空",
            has_actionable_items=False,
            todos=[],
            notifications=[],
            formatted_markdown="⚠️ 提示：未获取到有效文字内容。"
        )

    logger.info(f"文本内容通过初步检查，长度: {len(raw_text)} 字符。正在移交 AI 大脑...")

    # 3. 交给 AI 大脑处理 (带发言人画像与三维分类)
    result = extract_campus_info(raw_text, group_name=payload.source or "剪贴板/快捷指令")

    # 4. 自动同步写入 macOS Apple 原生「提醒事项 / 日历」（通过 iCloud 自动同步到 iPhone）
    from app.apple_sync import add_to_apple_reminders, add_to_apple_calendar, parse_datetime
    from app.database import is_item_already_synced, record_synced_item
    synced_count = 0
    for todo in result.todos:
        try:
            # 幂等去重：若此前已同步过相同任务指纹，不再重复录入苹果系统
            if todo.item_fingerprint and is_item_already_synced(todo.item_fingerprint):
                logger.info(f"⏭️ 待办【{todo.title}】已存在于本地数据库存根中，跳过重复写入 Apple Reminders。")
                continue

            dt = parse_datetime(todo.due_datetime)
            notes = f"地点/平台: {todo.location or '未指定'}\n详情: {todo.action_item}\n发布人: {todo.speaker or '群聊'}\n来源: Campus-Agent 自动提取"
            receipt = None
            if todo.is_calendar_event and dt:
                receipt = add_to_apple_calendar(todo.title, dt, notes=notes)
            else:
                receipt = add_to_apple_reminders(todo.title, due_datetime=dt, notes=notes, priority=1, category=todo.category)
            
            if receipt:
                synced_count += 1
                todo.receipt = receipt
                record_synced_item(
                    group_name=payload.source or "unknown",
                    fingerprint=todo.item_fingerprint or "legacy",
                    title=todo.title,
                    due_datetime=todo.due_datetime or "",
                    category=todo.category,
                    apple_item_id=receipt.get("apple_id", ""),
                    verified=True
                )
        except Exception as sync_err:
            logger.warning(f"同步 Apple 待办事项异常: {sync_err}")

    if synced_count > 0:
        logger.info(f"🎉 成功同步 {synced_count} 条待办至 Apple 官方提醒事项/日历！")

    # 5. 记入本地 SQLite 日志
    summary_preview = result.formatted_markdown[:100] if result.formatted_markdown else ""
    log_request(
        token=payload.token,
        source=payload.source or "unknown",
        raw_content=raw_text,
        has_actionable=result.has_actionable_items,
        summary=summary_preview
    )

    return result

# ================= 可视化群组管理与 RPA 巡检接口 =================

@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    """打开可视化控制台页面，支持勾选群和设置巡检间隔"""
    if DASHBOARD_FILE.exists():
        return DASHBOARD_FILE.read_text(encoding="utf-8")
    return "<h1>Dashboard 文件未找到</h1>"

@app.get("/naiwa", response_class=HTMLResponse)
def get_naiwa_widget():
    """打开奶蛙 (NaiWa) 动态角色与动画交互预览页面"""
    if NAIWA_WIDGET_FILE.exists():
        return NAIWA_WIDGET_FILE.read_text(encoding="utf-8")
    return "<h1>NaiWa Widget 文件未找到</h1>"


@app.get("/api/v1/groups")
def api_get_groups():
    """获取当前已配置的群列表及勾选状态"""
    return load_group_config()

@app.post("/api/v1/groups")
def api_save_groups(payload: dict):
    """保存用户在控制台上修改的群勾选状态或间隔"""
    save_group_config(payload)
    return {"status": "success", "message": "配置已保存"}

@app.get("/api/v1/groups/presets")
def api_get_group_presets():
    """获取智能规则预设模板库 (课程大作业/年级行政/社团讲座/宿舍生活)"""
    return get_rule_presets()

@app.get("/api/v1/groups/rule")
def api_get_single_group_rule(name: str):
    """获取单个群组的完整画像与过滤规则"""
    return get_group_rule(name)

@app.post("/api/v1/groups/rule")
def api_update_single_group_rule(payload: dict):
    """保存或更新单个群组的画像与过滤规则"""
    name = payload.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="必须提供群组名称 (name)")
    update_group_rule(name, payload)
    return {
        "status": "success",
        "message": f"群组【{name}】画像规则已更新",
        "rule": get_group_rule(name)
    }

@app.post("/api/v1/rpa/inspect")
def api_trigger_rpa_inspect(force: bool = False):
    """手动或定时触发全量群聊巡查"""
    logger.info(f"收到立即执行群聊巡检指令 (force={force})...")
    result = execute_batch_inspection(max_scroll_pages=3, force=force)
    return result

@app.post("/api/v1/rpa/inspect_current")
def api_trigger_inspect_current(force: bool = False):
    """零按键安全模式：直接提取当前屏幕上打开的微信群聊"""
    logger.info(f"收到抓取当前活跃群聊指令 (force={force})...")
    return inspect_current_active_chat(force=force)

@app.get("/api/v1/synced_items")
def api_get_synced_items():
    """获取所有已验真回执的待办与日程列表 (Bi-directional Receipts)"""
    from app.database import get_recent_synced_items
    return get_recent_synced_items(limit=30)

# ================= 后台定时守护巡检与高危 DDL 预警接口 =================

@app.get("/api/v1/daemon/status")
def api_get_daemon_status():
    """获取守护调度器全量实时状态（包含运行状态、空闲秒数、下次预计时间、高危告警历史）"""
    from app.scheduler_daemon import daemon_scheduler
    return daemon_scheduler.get_status()

@app.post("/api/v1/daemon/toggle")
def api_toggle_daemon(payload: dict):
    """开启或暂停后台守护巡检"""
    from app.scheduler_daemon import daemon_scheduler
    enabled = payload.get("enabled", True)
    new_state = daemon_scheduler.set_enabled(enabled)
    return {"status": "success", "is_enabled": new_state, "message": f"守护巡检已{'开启' if new_state else '暂停'}"}

@app.post("/api/v1/daemon/interval")
def api_set_daemon_interval(payload: dict):
    """设置守护巡检周期（分钟）"""
    from app.scheduler_daemon import daemon_scheduler
    minutes = payload.get("interval_minutes", 30)
    new_interval = daemon_scheduler.set_interval(minutes)
    return {"status": "success", "interval_minutes": new_interval, "message": f"巡检周期已更新为 {new_interval} 分钟"}

@app.post("/api/v1/daemon/trigger")
async def api_trigger_daemon_patrol(force: bool = True):
    """手动立即触发一轮后台守护巡查"""
    from app.scheduler_daemon import daemon_scheduler
    res = await asyncio.to_thread(daemon_scheduler.patrol_cycle, force=force)
    return res

@app.post("/api/v1/daemon/test_alert")
def api_test_daemon_alert():
    """模拟测试高危 DDL 预警：现场体验 Mac 原生横幅通知 + 硬件扬声器奶龙原声大叫与口播"""
    from app.scheduler_daemon import daemon_scheduler
    return daemon_scheduler.test_simulate_alert()

class CopilotChatRequest(BaseModel):
    message: str
    history: Optional[List[dict]] = None

@app.post("/api/v1/copilot/chat")
def api_copilot_chat(payload: CopilotChatRequest):
    """
    Campus-Copilot 校园智能学伴对话接口：
    支持向用户主动预警注意事项、DDL 答疑以及调用端侧工具
    """
    from app.agent import chat_with_copilot
    return chat_with_copilot(user_message=payload.message, history=payload.history)

@app.get("/api/v1/copilot/latest_briefing")
def api_get_latest_briefing():
    """获取智能学伴奶蛙最新生成的巡视简报与口播文案"""
    from app.agent import get_latest_briefing
    return get_latest_briefing()

class SpeakRequest(BaseModel):
    text: str
    voice: Optional[str] = "NaiLong"

@app.post("/api/v1/copilot/speak")
def api_speak_briefing(payload: SpeakRequest):
    """【用户已停用声音】"""
    return {"status": "disabled", "message": "声音模块已全量停用"}

class NaiLongTTSRequest(BaseModel):
    text: str
    play_on_mac: bool = False

@app.post("/api/v1/copilot/tts_nailong")
def api_tts_nailong(payload: NaiLongTTSRequest):
    """【用户已停用声音】"""
    return {"status": "disabled", "audio_url": None, "message": "声音模块已全量停用"}

class PlaySoundRequest(BaseModel):
    sound: str = "laugh"
    play_on_mac: bool = False

@app.post("/api/v1/copilot/play_sound")
def api_play_sound(payload: PlaySoundRequest):
    """【用户已停用声音】"""
    return {"status": "disabled", "sound_url": None, "message": "声音模块已全量停用"}

@app.get("/api/v1/copilot/nailong_preset")
def api_nailong_preset(event: str = "laugh", play_on_mac: bool = False):
    """【用户已停用声音】"""
    return {"status": "disabled", "audio_url": None, "message": "声音模块已全量停用"}



# ================= macOS 顶部状态栏常驻胶囊 (MenuBar Pill) 接口 =================

@app.get("/api/v1/menubar/status")
def api_get_menubar_status():
    """获取 macOS 状态栏常驻胶囊运行状态与 PID"""
    from app.menubar_manager import menubar_manager
    return menubar_manager.get_status()

@app.post("/api/v1/menubar/start")
def api_start_menubar():
    """启动 macOS 顶部状态栏常驻小胶囊"""
    from app.menubar_manager import menubar_manager
    return menubar_manager.start()

@app.post("/api/v1/menubar/stop")
def api_stop_menubar():
    """安全停止并退出 macOS 顶部状态栏常驻小胶囊"""
    from app.menubar_manager import menubar_manager
    return menubar_manager.stop()






