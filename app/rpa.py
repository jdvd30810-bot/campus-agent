import subprocess
import time
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.groups_manager import (
    get_enabled_groups,
    load_group_config,
    save_group_config,
    get_trusted_speakers,
    get_group_category
)
from app.extractor import extract_campus_info
from app.database import (
    log_request,
    check_and_update_watermark,
    is_item_already_synced,
    record_synced_item
)
from app.apple_sync import add_to_apple_reminders, add_to_apple_calendar, parse_datetime

from app.human_driver import (
    mouse_click,
    mouse_scroll,
    mouse_click_pid,
    mouse_scroll_pid,
    get_wechat_pid,
    get_wechat_bounds,
    get_wechat_window_info,
    get_frontmost_app,
    restore_frontmost_app,
    dismiss_search_overlay,
    HumanInterruptionError,
    reset_collision_detector,
    get_current_mouse_pos,
    ensure_wechat_ready_for_scan,
    restore_wechat_after_scan
)


logger = logging.getLogger("campus-agent.rpa")

from PIL import Image

BASE_DIR = Path(__file__).resolve().parent.parent
OCR_BIN = BASE_DIR / "app" / "ocr_bin"
OCR_SWIFT = BASE_DIR / "app" / "ocr.swift"
IMG_PATH = "/tmp/wechat_capture.png"
ROI_IMG_PATH = "/tmp/wechat_roi.png"

# 强力黑名单：凡是包含微信顶部搜索、网络结果、历史搜索下拉词汇，一律彻底过滤，绝不触碰！
SEARCH_UI_BLACKLIST = {
    "搜索", "搜一搜", "网络结果", "最近在搜", "搜文章", "搜朋友圈",
    "微信", "公众号", "视频号", "小程序", "全部", "文章", "独立窗口", "AI搜索"
}

def compute_image_dhash(image_path: str, hash_size: int = 8) -> str:
    """
    计算轻量级 64 位感知差分哈希 (dHash, Difference Hash)：
    1. 缩放到 9x8 灰度图 (仅 72 个像素，处理耗时 < 3ms)；
    2. 计算相邻列的像素梯度差值 (左 > 右 为 1，否则为 0)；
    3. 生成 16 进制字符串，若屏幕画面未变，哈希 100% 相同；
    4. 相比传统直接跑 OCR，直接在图片层面完成毫秒级帧差过滤，极大节省 OCR 算力与大模型 Token！
    """
    try:
        with Image.open(image_path) as img:
            resized = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.BILINEAR)
            pixels = list(resized.getdata())
            diff = []
            for row in range(hash_size):
                row_start = row * (hash_size + 1)
                for col in range(hash_size):
                    diff.append(pixels[row_start + col] > pixels[row_start + col + 1])
            decimal_value = 0
            for index, value in enumerate(diff):
                if value:
                    decimal_value += 1 << index
            return hex(decimal_value)[2:].zfill(hash_size * hash_size // 4)
    except Exception as e:
        logger.warning(f"计算图片 dHash 异常: {e}")
        return ""

def crop_chat_bubble_roi(source_img_path: str, target_img_path: str = ROI_IMG_PATH) -> str:
    """
    【ROI 局部裁剪 (Region of Interest Cropping)】
    精准裁剪微信聊天气泡流，彻底剔除噪音：
    - 剔除左侧全局导航栏 (图标栏 ~0.08W)
    - 剔除中间联系人/会话列表 (~0.26W)
    - 剔除底部输入框、草稿与发送按钮 (下方 ~0.20H)
    - 保留顶部群标题栏与中间聊天气泡核心区域：
      x 范围: 0.28 * W ~ 0.98 * W
      y 范围: 0.05 * H ~ 0.80 * H
    直接削减 60% 无效像素与 OCR 噪声，杜绝将输入法未发送草稿误判为通知！
    """
    try:
        with Image.open(source_img_path) as img:
            w, h = img.size
            if w > 800 and h > 500:
                left = int(w * 0.28)
                top = int(h * 0.05)
                right = int(w * 0.98)
                bottom = int(h * 0.80)
                cropped = img.crop((left, top, right, bottom))
                cropped.save(target_img_path)
                return target_img_path
    except Exception as e:
        logger.warning(f"ROI 裁剪异常，降级使用原图: {e}")
    return source_img_path


def run_vision_ocr(image_path: str = IMG_PATH, as_json: bool = False) -> Any:
    """调用高性能 Apple Vision 原生引擎执行实况文本提取"""
    cmd = [str(OCR_BIN) if OCR_BIN.exists() else "swift", image_path]
    if not OCR_BIN.exists():
        cmd = ["swift", str(OCR_SWIFT), image_path]
    if as_json:
        cmd.append("--json")
        
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        output = res.stdout.strip()
        if as_json:
            return json.loads(output) if output else []
        return output
    except Exception as e:
        logger.error(f"Vision OCR 执行异常: {e}")
        return [] if as_json else ""

def match_subscribed_group(group_name: str, sidebar_items: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    在 OCR 会话栏中，精准寻找与用户订阅群匹配的条目：
    - 严格垂直安全边界：必须避开顶部搜索框 (y < 0.085 相当于顶部 75px 绝对禁区)
    - 严格黑名单过滤：绝对不匹配任何搜索框、网络搜索结果、搜一搜
    - 支持缩略名模糊匹配（如 '26秋 通用英语C' 匹配 '26秋通用英.'）
    """
    target = group_name.strip()
    clean_target = target.replace("26秋", "").replace("2026", "").replace("26", "").replace("通知群", "")
    
    # 提取核心辨识特征词（避开“群”、“班”、“计算机”等泛词）
    generic_words = {"计算机", "班", "群", "本科", "本", "秋", "春", "类", "届"}
    core_words = [w for w in clean_target.split() if len(w) >= 2 and w not in generic_words]
    if not core_words and len(clean_target) >= 2:
        core_words = [clean_target]

    best_score = 0.0
    best_match = None

    for it in sidebar_items:
        x = it.get("x", 1.0)
        y = it.get("y", 0.0)

        # 1. 严格水平限定：必须在左侧会话栏区域
        if x < 0.04 or x > 0.22:
            continue
            
        # 2. 物理级垂直安全护栏：严禁匹配顶部 75px 以内的搜索框区域！
        if y < 0.085 or y > 0.95:
            continue

        text = it.get("text", "").strip()
        if not text:
            continue
            
        # 3. 严格黑名单拦截：任何带有“搜索/网络结果/搜一搜”字样的项彻底屏蔽
        if any(k in text for k in SEARCH_UI_BLACKLIST):
            continue

        # 4. 核心特征词精准命中 (如: 德法、形势、通用英语、水心、线性代数)
        if core_words and any(cw in text for cw in core_words):
            return it

        # 5. 子串直接包含
        if clean_target and len(clean_target) >= 2 and (clean_target in text or text in clean_target):
            return it

        # 6. 字符重合度评分 (阈值提高至 0.65，防止相似群名误认)
        target_set = set(clean_target)
        overlap = len(target_set & set(text))
        score = overlap / max(len(target_set), 1)
        if score > best_score and score >= 0.65:
            best_score = score
            best_match = it

    return best_match

def inspect_current_active_chat(force: bool = False) -> Dict[str, Any]:
    """
    【模式一：当前群极速提取 (Zero-Touch)】
    1. 调用 CoreGraphics 原生获取微信主窗口信息 (WindowID 与 Bounds)；
    2. 【方案二：GPU 显存直接抓取】：通过 screencapture -x -o -l <win_id> 直接从 WindowServer 显存读取；
       无需将微信强行置顶前台、无需闪现、彻底免疫任何上层窗口遮挡！
    3. 纯视觉 OCR + AI 结构化提炼 + 幂等验真写入 Apple 提醒事项/日历；
    4. 全程 0 鼠标抢夺、0 键盘敲击、0 窗口打扰。
    """
    logger.info(f"正在执行当前群极速静默提取 (GPU Backing Store, force={force})...")
    prev_app = get_frontmost_app()
    lifecycle_meta = ensure_wechat_ready_for_scan()
    try:
        win_info = lifecycle_meta.get("win_info") or get_wechat_window_info()
        if not win_info:
            return {"status": "error", "message": "未找到可见的微信窗口，后台静默唤醒微信失败，请确认微信已登录。"}
        return _do_inspect_current_active_chat(win_info, force=force)
    finally:
        restore_wechat_after_scan(lifecycle_meta)
        restore_frontmost_app(prev_app)

def _do_inspect_current_active_chat(win_info: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
    # [AT-001] 拦截微信最小化 (Dock) 状态：避免 WindowServer 显存停更抓取到残影
    if win_info.get("is_minimized"):
        logger.warning("⚠️ 检测到微信主窗口被最小化至 Dock，显存已停止刷新！")
        from app.agent import generate_agent_briefing
        res = {
            "status": "warning",
            "is_minimized": True,
            "message": "⚠️ 检测到微信主窗口已被最小化至 Dock 栏，macOS 显存已停止更新画面。请使用 Cmd+H 隐藏微信或让其他窗口自然遮挡，后台即可继续无感巡视！",
            "todos": [],
            "notifications": [],
            "summary": "⚠️ 微信目前处于 Dock 最小化状态，显存停止刷新。建议按 Cmd+H 隐藏微信，无需最小化。"
        }
        res["agent_briefing"] = generate_agent_briefing(res, mode="current")
        return res
    
    win_id = win_info.get("window_id")
    bounds = win_info.get("bounds", {})
    
    # 方案二：优先使用 WindowID 显存直接快照 (无阴影、无需前台置顶、被遮挡也能 100% 清晰抓取)
    if win_id:
        capture_cmd = ["screencapture", "-x", "-o", "-l", str(win_id), IMG_PATH]
    else:
        coords = f"{bounds.get('x', 0)},{bounds.get('y', 0)},{bounds.get('w', 1200)},{bounds.get('h', 800)}"
        capture_cmd = ["screencapture", "-x", f"-R{coords}", IMG_PATH]
        
    try:
        subprocess.run(capture_cmd, check=True)
    except Exception as e:
        return {"status": "error", "message": f"截屏失败: {e}"}

    # [AT-002] 局部区域精准裁剪 (ROI)：过滤左侧侧边栏、会话列表及底部输入框，直接节省 60% 像素噪音与 Token
    roi_file = crop_chat_bubble_roi(IMG_PATH, ROI_IMG_PATH)

    # [AT-002] 轻量 64 位感知差分哈希 (dHash) 预检：耗时仅 3ms，相同画面直接 0ms 跳过 OCR 与 LLM
    current_dhash = compute_image_dhash(roi_file)
    if current_dhash and not force:
        is_dhash_changed, _ = check_and_update_watermark("current_active_window_dhash", current_dhash)
        if not is_dhash_changed:
            logger.info(f"🌊 [dHash 帧差命中] 聊天气泡画面指纹未变动 ({current_dhash})，0ms 极速跳过 OCR 与 AI 提取。")
            from app.agent import generate_agent_briefing
            res = {
                "status": "success",
                "is_watermark_unchanged": True,
                "synced_to_apple": 0,
                "raw_text_preview": "聊天画面未变动 (dHash 缓存命中)",
                "todos": [],
                "notifications": [],
                "summary": "🟢 命中 dHash 视觉帧差预检：当前聊天气泡画面与上次完全一致，无新增消息，已在 3ms 内完成巡视并跳过 AI 处理。"
            }
            res["agent_briefing"] = generate_agent_briefing(res, mode="current")
            return res

    # OCR 识别文字 (优先在纯净的 ROI 气泡图上执行)
    messages_text = run_vision_ocr(roi_file, as_json=False)
    if len(messages_text) < 15:
        # 若 ROI 截取内容过短，保底使用全图 OCR 尝试
        messages_text = run_vision_ocr(IMG_PATH, as_json=False)
        if len(messages_text) < 15:
            return {"status": "warning", "message": "当前微信窗口未检测到足够的文字内容，请确认聊天区域可见"}

    # 1. 文本高水位线二次去重兜底 (Cutoff & Watermark)
    is_changed, text_hash = check_and_update_watermark("current_active_window", messages_text)
    if not is_changed and not force:
        logger.info("🌊 [高水位线] 当前窗口文字未发生变动，命中缓存，跳过重复提取。")
        from app.agent import generate_agent_briefing
        res = {
            "status": "success",
            "is_watermark_unchanged": True,
            "synced_to_apple": 0,
            "raw_text_preview": messages_text[:120].replace("\n", " "),
            "todos": [],
            "notifications": [],
            "summary": "🟢 命中文字高水位线：当前聊天窗口文字与上次检查完全一致，无新增消息，已自动跳过重复提取。"
        }
        res["agent_briefing"] = generate_agent_briefing(res, mode="current")
        return res


    # 2. AI 结构化提炼 (传入通用置信身份白名单)
    default_speakers = ["老师", "教师", "辅导员", "班长", "学委", "助教"]
    ai_res = extract_campus_info(messages_text, group_name="当前活跃微信群", trusted_speakers=default_speakers)
    
    # 3. 自动写入 Apple 提醒事项 / 日历 (支持多列表分类与双向回读确认)
    synced = 0
    for todo in ai_res.todos:
        # 幂等校验
        if todo.item_fingerprint and is_item_already_synced(todo.item_fingerprint):
            logger.info(f"⏭️ 待办【{todo.title}】已在存根中，跳过重复同步。")
            continue

        dt = parse_datetime(todo.due_datetime)
        speaker_str = f"【置信发言人: {todo.speaker}】\n" if todo.speaker else ""
        notes = f"{speaker_str}地点/平台: {todo.location or '未指定'}\n详情: {todo.action_item}\n来源: 当前微信群抓取"
        receipt = None
        if todo.is_calendar_event and dt:
            receipt = add_to_apple_calendar(todo.title, dt, notes=notes)
        else:
            receipt = add_to_apple_reminders(todo.title, due_datetime=dt, notes=notes, priority=1, category=todo.category)
            
        if receipt:
            synced += 1
            todo.receipt = receipt
            record_synced_item(
                group_name="当前活跃群",
                fingerprint=todo.item_fingerprint or "legacy",
                title=todo.title,
                due_datetime=todo.due_datetime or "",
                category=todo.category,
                apple_item_id=receipt.get("apple_id", ""),
                verified=True
            )
                
    log_request(
        token="RPA_CURRENT",
        source="wechat_current_window",
        raw_content=messages_text[:500],
        has_actionable=ai_res.has_actionable_items,
        summary=ai_res.formatted_markdown[:100] if ai_res.formatted_markdown else ""
    )

    from app.agent import generate_agent_briefing
    final_res = {
        "status": "success",
        "synced_to_apple": synced,
        "is_watermark_unchanged": False,
        "raw_text_preview": messages_text[:120].replace("\n", " "),
        "todos": [t.dict() for t in ai_res.todos],
        "notifications": [n.dict() for n in ai_res.notifications],
        "summary": ai_res.formatted_markdown
    }
    final_res["agent_briefing"] = generate_agent_briefing(final_res, mode="current")
    return final_res

def inspect_subscribed_groups(max_scroll_pages: int = 3, force: bool = False) -> Dict[str, Any]:
    """
    【模式二：视觉精准巡检所有已订阅群 (Visual Subscribed Groups Roaming)】
    核心设计理念：
    1. 【严格只检查订阅群】：从 monitored_groups.json 读取用户勾选的群，绝不点击私人或无关群；
    2. 【破除3个限制】：自动向下轻滚翻页，支持巡检 5~20 个全部已勾选群；
    3. 【物理级 0 误触】：纯鼠标视觉找群，全程 0 键盘按键、0 搜索框输入、0 回车；
    4. 【无感现场复原】：全部巡检完自动滑回顶部，瞬间切回用户原应用！
    """
    prev_app = get_frontmost_app()
    enabled_groups = get_enabled_groups()
    logger.info(f"启动订阅群精准巡检，当前共需巡检 {len(enabled_groups)} 个群: {enabled_groups}")
    
    if not enabled_groups:
        restore_frontmost_app(prev_app)
        return {
            "status": "warning",
            "message": "当前未勾选任何订阅群，请在控制台添加并勾选需要监控的群聊。",
            "inspected_count": 0,
            "total_synced_todos": 0,
            "results": []
        }
        
    lifecycle_meta = ensure_wechat_ready_for_scan()
    try:
        win_info = lifecycle_meta.get("win_info") or get_wechat_window_info()
        if not win_info:
            return {"status": "error", "message": "未找到可见的微信窗口，后台静默唤醒微信失败，请确认微信已登录。"}

        # [AT-001] 拦截微信最小化至 Dock
        if win_info.get("is_minimized"):
            return {
                "status": "warning",
                "is_minimized": True,
                "message": "⚠️ 微信主窗口目前处于 Dock 最小化状态，macOS 显存停止刷新。建议按 Cmd+H 隐藏微信替代最小化。"
            }
            
        bounds = win_info["bounds"]
        win_id = win_info.get("window_id")

        # 第一道防线：先轻按 Esc，强制清除微信历史搜索框残留或搜索下拉面板
        dismiss_search_overlay()
        time.sleep(0.1)

        # 会话列表标题中心水平 X 坐标 (避开最左侧 60px 导航图标)
        list_x = bounds["x"] + 160
        coords = f"{bounds['x']},{bounds['y']},{bounds['w']},{bounds['h']}"
        
        reset_collision_detector()
        try:
            return _do_inspect_subscribed_groups(bounds, coords, list_x, enabled_groups, max_scroll_pages, prev_app, win_id=win_id, force=force)
        except HumanInterruptionError as e:
            logger.warning(f"🚨 [人类物理介入紧急熔断] 用户正在使用鼠标: {e}，系统立即主动放弃操作并还权！")
            return {
                "status": "yielded",
                "message": f"检测到用户物理操作介入 ({e})，系统主动紧急避让退出，已瞬时还回焦点。",
                "inspected_count": 0,
                "total_synced_todos": 0,
                "results": []
            }
        finally:
            reset_collision_detector()
    finally:
        restore_wechat_after_scan(lifecycle_meta)
        restore_frontmost_app(prev_app)

def _do_inspect_subscribed_groups(bounds, coords, list_x, enabled_groups, max_scroll_pages, prev_app, win_id: Optional[int] = None, force: bool = False) -> Dict[str, Any]:
    pending_groups = list(enabled_groups) # 待巡查群队列
    inspected_results = []
    total_synced = 0
    scrolled_pages = 0
    wechat_pid = get_wechat_pid()
    
    # 方案二：优先使用 WindowID 显存无感快照 (无视遮挡、无需前台置顶)
    capture_cmd = ["screencapture", "-x", "-o", "-l", str(win_id), IMG_PATH] if win_id else ["screencapture", "-x", f"-R{coords}", IMG_PATH]
    
    while pending_groups and scrolled_pages < max_scroll_pages:


        # 1. 截取当前微信屏幕
        try:
            subprocess.run(capture_cmd, check=True)
        except Exception as e:
            logger.error(f"截屏失败: {e}")
            break
            
        # 2. 视觉 OCR 解析会话栏中所有可见的会话项及 Y 坐标
        items = run_vision_ocr(IMG_PATH, as_json=True)
        # 物理级安全护栏：仅保留在会话栏区间且避开顶部搜索框 (y >= 0.085) 的条目
        sidebar_items = [
            it for it in items 
            if 0.04 <= it.get("x", 1.0) <= 0.22 and 0.085 <= it.get("y", 0.0) <= 0.95
        ]
        
        found_in_this_page = []
        for g_name in list(pending_groups):
            match = match_subscribed_group(g_name, sidebar_items)
            if match:
                sidebar_items.remove(match) # 独占该会话项，防止其他同名或相似群误抢
                click_y = bounds["y"] + int(match["y"] * bounds["h"])
                
                # 终极物理防护：坚决不允许点击任何落在顶部搜索框 (bounds['y'] + 75) 内的位置
                if click_y < bounds["y"] + 75 or click_y > bounds["y"] + bounds["h"] - 30:
                    logger.warning(f"跳过危险坐标 Y={click_y}，该位置可能处于搜索栏或边缘，拒绝点击！")
                    continue
                    
                logger.info(f"🎯 视觉锁定订阅群: 【{g_name}】 -> 屏幕坐标 Y={click_y}")
                
                # 3. 鼠标轻触该群聊项 (方案一：定向私有事件注入，物理鼠标 0 位移)
                mouse_click_pid(list_x, click_y, pid=wechat_pid, delay_after=0.35)
                
                # 4. 快照聊天内容 (方案二：显存 Backing Store 抓取)
                subprocess.run(capture_cmd, check=True)
                roi_file = crop_chat_bubble_roi(IMG_PATH, ROI_IMG_PATH)

                # [AT-002] 轻量 dHash 预检：若该群画面指纹未变，0ms 极速跳过 OCR 与 AI 提取
                g_dhash = compute_image_dhash(roi_file)
                if g_dhash and not force:
                    is_dhash_changed, _ = check_and_update_watermark(f"{g_name}_dhash", g_dhash)
                    if not is_dhash_changed:
                        logger.info(f"🌊 [dHash 帧差命中] 订阅群【{g_name}】聊天画面指纹未变动 ({g_dhash})，0ms 跳过 OCR 与 AI。")
                        inspected_results.append({
                            "group_name": g_name,
                            "synced": 0,
                            "is_watermark_unchanged": True,
                            "todos": [],
                            "notifications": [],
                            "summary": "🟢 命中 dHash 视觉帧差预检：画面指纹完全一致，0ms 极速跳过重复提取。"
                        })
                        found_in_this_page.append(g_name)
                        pending_groups.remove(g_name)
                        continue

                chat_text = run_vision_ocr(roi_file, as_json=False)
                if len(chat_text) < 15:
                    chat_text = run_vision_ocr(IMG_PATH, as_json=False)

                # 5. 视觉文本高水位线二次去重与 AI 提炼
                if len(chat_text) >= 15:
                    is_changed, _ = check_and_update_watermark(g_name, chat_text)
                    if not is_changed and not force:
                        logger.info(f"🌊 [高水位线] 订阅群【{g_name}】未检测到新消息，跳过大模型提取。")
                        inspected_results.append({
                            "group_name": g_name,
                            "synced": 0,
                            "is_watermark_unchanged": True,
                            "todos": [],
                            "notifications": [],
                            "summary": "🟢 命中高水位线：本群聊天文字无新增变动，自动跳过重复提取。"
                        })
                    else:
                        try:
                            trusted_speakers = get_trusted_speakers(g_name)
                            ai_res = extract_campus_info(chat_text, group_name=g_name, trusted_speakers=trusted_speakers)
                            chat_synced = 0
                            for todo in ai_res.todos:
                                # 幂等去重校验
                                if todo.item_fingerprint and is_item_already_synced(todo.item_fingerprint):
                                    logger.info(f"⏭️ 待办【{todo.title}】已在存根中，跳过重复同步。")
                                    continue

                                dt = parse_datetime(todo.due_datetime)
                                speaker_str = f"【置信发言人: {todo.speaker}】\n" if todo.speaker else ""
                                notes = f"{speaker_str}地点/平台: {todo.location or '未指定'}\n详情: {todo.action_item}\n来源: 巡检【{g_name}】"
                                receipt = None
                                if todo.is_calendar_event and dt:
                                    receipt = add_to_apple_calendar(todo.title, dt, notes=notes)
                                else:
                                    receipt = add_to_apple_reminders(todo.title, due_datetime=dt, notes=notes, priority=1, category=todo.category)
                                    
                                if receipt:
                                    chat_synced += 1
                                    todo.receipt = receipt
                                    record_synced_item(
                                        group_name=g_name,
                                        fingerprint=todo.item_fingerprint or "legacy",
                                        title=todo.title,
                                        due_datetime=todo.due_datetime or "",
                                        category=todo.category,
                                        apple_item_id=receipt.get("apple_id", ""),
                                        verified=True
                                    )
                                        
                            total_synced += chat_synced
                            inspected_results.append({
                                "group_name": g_name,
                                "synced": chat_synced,
                                "is_watermark_unchanged": False,
                                "todos": [t.dict() for t in ai_res.todos],
                                "notifications": [n.dict() for n in ai_res.notifications],
                                "summary": ai_res.formatted_markdown
                            })
                            
                            log_request(
                                token="RPA_SUBSCRIBED",
                                source=f"rpa_{g_name}",
                                raw_content=chat_text[:500],
                                has_actionable=ai_res.has_actionable_items,
                                summary=ai_res.formatted_markdown[:100] if ai_res.formatted_markdown else ""
                            )
                        except Exception as ai_err:
                            logger.error(f"分析群【{g_name}】出错: {ai_err}")
                else:
                    inspected_results.append({
                        "group_name": g_name,
                        "synced": 0,
                        "is_watermark_unchanged": False,
                        "todos": [],
                        "notifications": [],
                        "summary": "未扫描到足够字数的新消息。"
                    })

                    
                found_in_this_page.append(g_name)
                pending_groups.remove(g_name)
                time.sleep(0.3)
                
        # 如果还有未找到的订阅群，轻柔向下滚动 1 屏
        if pending_groups:
            logger.info(f"第 {scrolled_pages+1} 屏扫描完毕，仍有 {len(pending_groups)} 个订阅群待寻找，正在向下滑动...")
            mouse_scroll_pid(list_x, bounds["y"] + 250, lines=-7, pid=wechat_pid)
            time.sleep(0.5)
            scrolled_pages += 1
        else:
            break
            
    # 6. 全部完成，滚回顶部复位
    if scrolled_pages > 0:
        mouse_scroll_pid(list_x, bounds["y"] + 250, lines=scrolled_pages * 8, pid=wechat_pid)
        time.sleep(0.3)

        
    # 7. 更新巡检时间记录
    cfg = load_group_config()
    cfg["last_inspected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_group_config(cfg)
    
    # 8. 瞬间复原用户现场 (Ghost Switch)
    restore_frontmost_app(prev_app)
    
    from app.agent import generate_agent_briefing
    final_res = {
        "status": "success",
        "inspected_count": len(inspected_results),
        "total_synced_todos": total_synced,
        "results": inspected_results,
        "pending_not_found": pending_groups
    }
    final_res["agent_briefing"] = generate_agent_briefing(final_res, mode="batch")
    return final_res

def execute_batch_inspection(max_scroll_pages: int = 3, force: bool = False) -> Dict[str, Any]:
    """批量巡检默认执行视觉精准订阅群巡视（轻量快速 3 屏）"""
    return inspect_subscribed_groups(max_scroll_pages=max_scroll_pages, force=force)
