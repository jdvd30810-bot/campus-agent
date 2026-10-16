import ctypes
from ctypes import c_double, c_int32, c_uint32, c_void_p
import subprocess
import time
import logging
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("campus-agent.human_driver")

# =========================================================================
# 1. macOS 原生 CoreGraphics 底层图形引擎绑定 (严格 64 位 ABI 与指针安全)
# =========================================================================
CoreGraphics = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")

CoreFoundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

class CGPoint(ctypes.Structure):
    _fields_ = [("x", c_double), ("y", c_double)]

class CGSize(ctypes.Structure):
    _fields_ = [("width", c_double), ("height", c_double)]

class CGRect(ctypes.Structure):
    _fields_ = [("origin", CGPoint), ("size", CGSize)]

# 显式声明 64 位函数签名，坚决杜绝 32 位整数指针截断 (Pointer Truncation)
CoreGraphics.CGEventCreate.restype = c_void_p
CoreGraphics.CGEventCreate.argtypes = [c_void_p]

CoreGraphics.CGEventGetLocation.restype = CGPoint
CoreGraphics.CGEventGetLocation.argtypes = [c_void_p]

CoreGraphics.CGEventCreateMouseEvent.restype = c_void_p
CoreGraphics.CGEventCreateMouseEvent.argtypes = [c_void_p, c_uint32, CGPoint, c_uint32]

CoreGraphics.CGEventCreateScrollWheelEvent.restype = c_void_p
CoreGraphics.CGEventCreateScrollWheelEvent.argtypes = [c_void_p, c_uint32, c_uint32, c_int32]

CoreGraphics.CGEventPost.restype = None
CoreGraphics.CGEventPost.argtypes = [c_uint32, c_void_p]

# 方案一：定向进程事件注入 API (直接投递至目标进程事件队列，物理光标 0 位移)
CoreGraphics.CGEventPostToPid.restype = None
CoreGraphics.CGEventPostToPid.argtypes = [c_int32, c_void_p]

CoreGraphics.CGEventSetLocation.restype = None
CoreGraphics.CGEventSetLocation.argtypes = [c_void_p, CGPoint]

CoreGraphics.CGEventSetIntegerValueField.restype = None
CoreGraphics.CGEventSetIntegerValueField.argtypes = [c_void_p, c_int32, ctypes.c_int64]

# 方案二：CoreGraphics 窗口列表与显存帧缓冲 API (原生无感探测 WindowID 与几何坐标)
CoreGraphics.CGWindowListCopyWindowInfo.restype = c_void_p
CoreGraphics.CGWindowListCopyWindowInfo.argtypes = [c_uint32, c_uint32]

CoreGraphics.CGRectMakeWithDictionaryRepresentation.restype = ctypes.c_bool
CoreGraphics.CGRectMakeWithDictionaryRepresentation.argtypes = [c_void_p, ctypes.POINTER(CGRect)]

CoreFoundation.CFArrayGetCount.restype = ctypes.c_long
CoreFoundation.CFArrayGetCount.argtypes = [c_void_p]

CoreFoundation.CFArrayGetValueAtIndex.restype = c_void_p
CoreFoundation.CFArrayGetValueAtIndex.argtypes = [c_void_p, ctypes.c_long]

CoreFoundation.CFDictionaryGetValue.restype = c_void_p
CoreFoundation.CFDictionaryGetValue.argtypes = [c_void_p, c_void_p]

CoreFoundation.CFStringCreateWithCString.restype = c_void_p
CoreFoundation.CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, c_uint32]

CoreFoundation.CFStringGetCString.restype = ctypes.c_bool
CoreFoundation.CFStringGetCString.argtypes = [c_void_p, ctypes.c_char_p, ctypes.c_long, c_uint32]

CoreFoundation.CFNumberGetValue.restype = ctypes.c_bool
CoreFoundation.CFNumberGetValue.argtypes = [c_void_p, c_int32, c_void_p]

CoreFoundation.CFBooleanGetValue.restype = ctypes.c_bool
CoreFoundation.CFBooleanGetValue.argtypes = [c_void_p]

CoreFoundation.CFGetTypeID.restype = ctypes.c_ulong
CoreFoundation.CFGetTypeID.argtypes = [c_void_p]

CoreFoundation.CFBooleanGetTypeID.restype = ctypes.c_ulong
CoreFoundation.CFBooleanGetTypeID.argtypes = []

# CoreFoundation 内存释放严格 64 位 ABI 签名，彻底杜绝指针截断导致的 SIGSEGV 崩溃
CoreFoundation.CFRelease.restype = None
CoreFoundation.CFRelease.argtypes = [c_void_p]
CFRelease = CoreFoundation.CFRelease

kCFStringEncodingUTF8 = 0x08000100
_kOwner = CoreFoundation.CFStringCreateWithCString(None, b"kCGWindowOwnerName", kCFStringEncodingUTF8)
_kNumber = CoreFoundation.CFStringCreateWithCString(None, b"kCGWindowNumber", kCFStringEncodingUTF8)
_kBounds = CoreFoundation.CFStringCreateWithCString(None, b"kCGWindowBounds", kCFStringEncodingUTF8)
_kName = CoreFoundation.CFStringCreateWithCString(None, b"kCGWindowName", kCFStringEncodingUTF8)
_kIsOnscreen = CoreFoundation.CFStringCreateWithCString(None, b"kCGWindowIsOnscreen", kCFStringEncodingUTF8)


def _cf_to_str(cf_s) -> str:
    """CoreFoundation 字符串转 Python 字符串"""
    if not cf_s:
        return ""
    buf = ctypes.create_string_buffer(512)
    if CoreFoundation.CFStringGetCString(cf_s, buf, 512, kCFStringEncodingUTF8):
        return buf.value.decode("utf-8", errors="ignore")
    return ""

# 系统级输入事件空闲检测函数 (用于智能避让活跃用户)
CoreGraphics.CGEventSourceSecondsSinceLastEventType.restype = c_double
CoreGraphics.CGEventSourceSecondsSinceLastEventType.argtypes = [c_uint32, c_uint32]

def get_system_idle_seconds() -> float:
    """
    获取系统当前用户物理空闲时间（秒）：
    基于 macOS CoreGraphics 监听物理外设（鼠标与键盘）的最后触发时间戳。
    当用户正在使用电脑时，空闲秒数接近 0；当用户离开座位时，秒数持续增加。
    用于智能调度避让：用户在电脑前绝不抢占鼠标，用户离开时再静默巡查！
    """
    try:
        # 0 = kCGEventSourceStateCombinedSessionState, 0xFFFFFFFF = kCGAnyInputEventType
        return float(CoreGraphics.CGEventSourceSecondsSinceLastEventType(0, 0xFFFFFFFF))
    except Exception:
        return 0.0

def get_current_mouse_pos() -> tuple:
    """获取当前真实硬件光标的绝对物理屏幕坐标 (x, y)"""
    try:
        evt = CoreGraphics.CGEventCreate(None)
        if evt:
            loc = CoreGraphics.CGEventGetLocation(evt)
            CFRelease(evt)
            return (float(loc.x), float(loc.y))
    except Exception:
        pass
    return (0.0, 0.0)

# =========================================================================
# 物理人机碰撞熔断器 (Human Override & Dead Man's Switch)
# =========================================================================
class HumanInterruptionError(Exception):
    """用户物理干预异常：运行途中用户触碰、晃动或移动了鼠标，系统立即无条件熔断退出"""
    pass

_LAST_AGENT_POS = None

def reset_collision_detector():
    """重置碰撞熔断器状态"""
    global _LAST_AGENT_POS
    _LAST_AGENT_POS = None

def check_human_collision(tolerance_px: float = 35.0):
    """
    检查用户是否在后台运行中移动了鼠标。
    若物理坐标与 Agent 预定坐标偏差 > tolerance_px，说明人类介入，立即抛出异常熔断！
    """
    global _LAST_AGENT_POS
    if _LAST_AGENT_POS is None:
        return
    curr_x, curr_y = get_current_mouse_pos()
    last_x, last_y = _LAST_AGENT_POS
    dist = ((curr_x - last_x) ** 2 + (curr_y - last_y) ** 2) ** 0.5
    if dist > tolerance_px:
        logger.warning(f"🚨 [人类介入紧急熔断] 检测到用户物理移动了鼠标 (偏差 {dist:.1f}px > {tolerance_px}px)！立即停止一切自动化操作！")
        raise HumanInterruptionError(f"用户接管物理鼠标 (偏差 {dist:.1f}px)")

# macOS CGEvent 事件常量
CG_SESSION_EVENT_TAP = 1
EVENT_LEFT_DOWN = 1
EVENT_LEFT_UP = 2
EVENT_MOUSE_MOVED = 5

def mouse_move(x: float, y: float):
    """平滑移动鼠标光标至指定屏幕坐标"""
    global _LAST_AGENT_POS
    pt = CGPoint(x, y)
    evt = CoreGraphics.CGEventCreateMouseEvent(None, EVENT_MOUSE_MOVED, pt, 0)
    if evt:
        CoreGraphics.CGEventPost(CG_SESSION_EVENT_TAP, evt)
        CFRelease(evt)
    _LAST_AGENT_POS = (x, y)

def mouse_click(x: float, y: float, delay_after: float = 0.1):
    """
    在指定屏幕坐标触发带碰撞防护的物理仿真单击：
    1. 触发前先检测是否发生碰撞；
    2. 移动光标并微延时；
    3. 点击前再次核查光标是否停留在原定坐标（若用户移走光标，坚决不按下去！）；
    4. 抬起并更新 Agent 状态。
    """
    global _LAST_AGENT_POS
    
    # 0. 点击前检测是否已被用户打断
    check_human_collision()

    pt = CGPoint(x, y)
    
    # 1. 移动光标
    evt_move = CoreGraphics.CGEventCreateMouseEvent(None, EVENT_MOUSE_MOVED, pt, 0)
    if evt_move:
        CoreGraphics.CGEventPost(CG_SESSION_EVENT_TAP, evt_move)
        CFRelease(evt_move)
    _LAST_AGENT_POS = (x, y)
    time.sleep(0.02)
    
    # 2. 点击前再次安全确认：如果在这 20ms 内用户猛甩鼠标，坚决不按键！
    curr_x, curr_y = get_current_mouse_pos()
    if ((curr_x - x) ** 2 + (curr_y - y) ** 2) ** 0.5 > 25.0:
        logger.warning("🚨 用户在鼠标下按前一瞬间移动了光标，取消点击并触发熔断！")
        raise HumanInterruptionError("用户在点击前瞬移光标")

    # 3. 按下
    evt_down = CoreGraphics.CGEventCreateMouseEvent(None, EVENT_LEFT_DOWN, pt, 0)
    if evt_down:
        CoreGraphics.CGEventPost(CG_SESSION_EVENT_TAP, evt_down)
        CFRelease(evt_down)
    time.sleep(0.05)
    
    # 4. 抬起
    evt_up = CoreGraphics.CGEventCreateMouseEvent(None, EVENT_LEFT_UP, pt, 0)
    if evt_up:
        CoreGraphics.CGEventPost(CG_SESSION_EVENT_TAP, evt_up)
        CFRelease(evt_up)
    
    _LAST_AGENT_POS = (x, y)

    if delay_after > 0:
        time.sleep(delay_after)

def mouse_scroll(x: float, y: float, lines: int):
    """在指定位置模拟鼠标滚轮滚动，滚动前校验碰撞"""
    check_human_collision()
    mouse_move(x, y)
    time.sleep(0.05)
    
    evt_scroll = CoreGraphics.CGEventCreateScrollWheelEvent(None, 1, 1, lines)
    if evt_scroll:
        CoreGraphics.CGEventPost(CG_SESSION_EVENT_TAP, evt_scroll)
        CFRelease(evt_scroll)

# =========================================================================
# 方案一：定向私有事件投递 (Direct Process Event Injection · 物理鼠标 0 位移)
# =========================================================================

def get_wechat_pid() -> Optional[int]:
    """获取系统正在运行的 WeChat 进程 PID"""
    try:
        res = subprocess.run(["pgrep", "-x", "WeChat"], capture_output=True, text=True)
        out = res.stdout.strip()
        if out:
            return int(out.split()[0])
    except Exception:
        pass
    return None

def mouse_click_pid(x: float, y: float, pid: Optional[int] = None, delay_after: float = 0.1):
    """
    【方案一：定向私有事件注入】
    通过 CoreGraphics.CGEventPostToPid 将点击事件直接注入目标进程私有队列：
    1. 物理硬件光标位移量严格为 0.0px！人类正在使用鼠标时绝不受任何影响；
    2. 无需在全局系统广播 MouseMove，彻底杜绝光标抢占与对抗；
    3. 点击前后不移动用户正在使用的硬件光标。
    """
    if pid is None:
        pid = get_wechat_pid()
    
    pt = CGPoint(x, y)
    if pid:
        # 直接定向注入 WeChat 的私有事件队列
        evt_down = CoreGraphics.CGEventCreateMouseEvent(None, EVENT_LEFT_DOWN, pt, 0)
        if evt_down:
            CoreGraphics.CGEventSetIntegerValueField(evt_down, 1, 1) # kCGMouseEventClickState = 1
            CoreGraphics.CGEventPostToPid(pid, evt_down)
            CFRelease(evt_down)
        time.sleep(0.04)
        evt_up = CoreGraphics.CGEventCreateMouseEvent(None, EVENT_LEFT_UP, pt, 0)
        if evt_up:
            CoreGraphics.CGEventSetIntegerValueField(evt_up, 1, 1) # kCGMouseEventClickState = 1
            CoreGraphics.CGEventPostToPid(pid, evt_up)
            CFRelease(evt_up)
    else:
        mouse_click(x, y, delay_after=0)
    
    if delay_after > 0:
        time.sleep(delay_after)

def mouse_scroll_pid(x: float, y: float, lines: int, pid: Optional[int] = None):
    """向指定进程定向投递滚轮事件，物理光标 0 位移"""
    if pid is None:
        pid = get_wechat_pid()
    if pid:
        evt_scroll = CoreGraphics.CGEventCreateScrollWheelEvent(None, 1, 1, lines)
        if evt_scroll:
            CoreGraphics.CGEventSetLocation(evt_scroll, CGPoint(x, y))
            CoreGraphics.CGEventPostToPid(pid, evt_scroll)
            CFRelease(evt_scroll)
    else:
        mouse_scroll(x, y, lines)




# =========================================================================
# 2. 增强型微信窗口智能锁定与现场复原 (Ghost Switch)
# =========================================================================

def get_frontmost_app() -> str:
    """获取当前处于最前台的应用名称（用于巡检完毕后瞬间复原现场）"""
    script = '''
    tell application "System Events"
        return name of first application process whose frontmost is true
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return ""

def dismiss_search_overlay():
    """轻按 Esc 键强制退出任何搜索框焦点、历史搜索下拉浮层或搜一搜，确保回到纯净无干扰的会话列表"""
    script = '''
    tell application "System Events"
        if exists process "WeChat" then
            tell process "WeChat"
                key code 53
            end tell
        end if
    end tell
    '''
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=1.5)
    except Exception:
        pass

def restore_frontmost_app(app_name: str):
    """将屏幕焦点原封不动还给用户刚才正在使用的应用（如 VS Code、Chrome、Word 等）"""
    if not app_name or "wechat" in app_name.lower():
        return
    logger.info(f"RPA 任务完毕，正在将屏幕焦点无感复原至: 【{app_name}】")
    script = f'tell application "{app_name}" to activate'
    subprocess.run(["osascript", "-e", script], capture_output=True)

def get_wechat_window_info() -> Optional[Dict[str, Any]]:
    """
    【方案二：基于 CoreGraphics GPU 显存帧缓冲与 WindowID 精准探测】
    直接查询 macOS WindowServer 窗口列表：
    1. 彻底绕过易报权限错误 (-54 / -600) 的 AppleScript；
    2. 毫秒级锁定微信主聊天窗口 (过滤查看器、弹窗，挑选宽>600, 高>400 的最大主窗口)；
    3. 返回原生 WindowID 与屏幕绝对几何 Rect，供后台静默截屏 (screencapture -l) 与精准点击使用。
    """
    try:
        arr = CoreGraphics.CGWindowListCopyWindowInfo(0, 0)
        if not arr:
            return None
        cnt = CoreFoundation.CFArrayGetCount(arr)
        candidates = []
        for i in range(cnt):
            w = CoreFoundation.CFArrayGetValueAtIndex(arr, i)
            owner = _cf_to_str(CoreFoundation.CFDictionaryGetValue(w, _kOwner))
            if owner in ["微信", "WeChat"]:
                bounds_dict = CoreFoundation.CFDictionaryGetValue(w, _kBounds)
                rect = CGRect()
                if CoreGraphics.CGRectMakeWithDictionaryRepresentation(bounds_dict, ctypes.byref(rect)):
                    if rect.size.width > 600 and rect.size.height > 400:
                        num_cf = CoreFoundation.CFDictionaryGetValue(w, _kNumber)
                        win_id = c_uint32(0)
                        CoreFoundation.CFNumberGetValue(num_cf, 3, ctypes.byref(win_id))
                        name = _cf_to_str(CoreFoundation.CFDictionaryGetValue(w, _kName))
                        area = rect.size.width * rect.size.height

                        # [AT-001] 显存刷新与屏幕可见性检测：识别是否被黄色按钮最小化进 Dock
                        onscreen_cf = CoreFoundation.CFDictionaryGetValue(w, _kIsOnscreen)
                        is_onscreen = True
                        if onscreen_cf:
                            try:
                                if CoreFoundation.CFGetTypeID(onscreen_cf) == CoreFoundation.CFBooleanGetTypeID():
                                    is_onscreen = bool(CoreFoundation.CFBooleanGetValue(onscreen_cf))
                            except Exception:
                                is_onscreen = True


                        candidates.append({
                            "window_id": win_id.value,
                            "name": name,
                            "area": area,
                            "is_onscreen": is_onscreen,
                            "is_minimized": not is_onscreen,
                            "bounds": {
                                "x": int(rect.origin.x),
                                "y": int(rect.origin.y),
                                "w": int(rect.size.width),
                                "h": int(rect.size.height)
                            }
                        })
        CoreFoundation.CFRelease(arr)
        if not candidates:
            return None
        # 优先选择当前在屏幕上可见且面积最大的主聊天窗口
        candidates.sort(key=lambda c: (1 if c["is_onscreen"] else 0, 1 if c["name"] in ["微信", "WeChat", ""] else 0, c["area"]), reverse=True)
        return candidates[0]
    except Exception as e:
        logger.warning(f"CoreGraphics 获取微信窗口信息异常: {e}")
        return None

def get_wechat_bounds(activate: bool = False) -> Optional[Dict[str, int]]:
    """
    精准获取微信当前主窗口在屏幕上的坐标与宽高。
    优先采用纯原生 CoreGraphics C 接口（0 权限弹窗、0 毫秒级极速响应、不打扰前台）。
    若未找到且指定了 activate=True，则尝试轻量唤醒。
    """
    info = get_wechat_window_info()
    if info and info.get("bounds"):
        return info["bounds"]
        
    if activate:
        try:
            subprocess.run(["osascript", "-e", 'tell application "WeChat" to reopen'], capture_output=True, timeout=2)
            time.sleep(0.3)
            info = get_wechat_window_info()
            if info and info.get("bounds"):
                return info["bounds"]
        except Exception:
            pass
    return None

# =========================================================================
# 3. 微信无感生命周期守护器 (Zero-Trace WeChat Auto-Lifecycle)
# =========================================================================

def is_wechat_running() -> bool:
    """检测微信进程当前是否处于运行状态"""
    try:
        res = subprocess.run(["pgrep", "-x", "WeChat"], capture_output=True, text=True)
        return bool(res.stdout.strip())
    except Exception:
        return False

def ensure_wechat_ready_for_scan() -> Dict[str, Any]:
    """
    【微信无感生命周期守护：扫描前准备】
    返回初始状态元数据:
    {
        "was_running": bool,
        "was_window_open": bool,
        "win_info": Optional[dict]
    }
    若用户在扫描前未打开微信窗口，后台自动静默唤起主窗口并等待 GPU 帧缓冲就绪；
    全程保持 0 焦点抢夺，巡查完毕后依据该元数据执行精准复原。
    """
    was_running = is_wechat_running()
    win_info = get_wechat_window_info()
    was_window_open = bool(win_info and win_info.get("is_onscreen") and not win_info.get("is_minimized"))

    if not was_running:
        logger.info("微信未运行，正在后台静默唤醒 (open -g -a WeChat)...")
        try:
            subprocess.run(["open", "-g", "-a", "WeChat"], timeout=4)
            for _ in range(10):
                time.sleep(0.3)
                win_info = get_wechat_window_info()
                if win_info and win_info.get("is_onscreen"):
                    break
        except Exception as e:
            logger.warning(f"后台启动微信异常: {e}")
    elif not was_window_open:
        logger.info("微信进程在后台但窗口未展开，正在静默唤醒主窗口 (reopen)...")
        try:
            subprocess.run(["osascript", "-e", 'tell application "WeChat" to reopen'], capture_output=True, timeout=2)
            for _ in range(8):
                time.sleep(0.25)
                win_info = get_wechat_window_info()
                if win_info and win_info.get("is_onscreen"):
                    break
        except Exception as e:
            logger.warning(f"唤醒微信主窗口异常: {e}")

    return {
        "was_running": was_running,
        "was_window_open": was_window_open,
        "win_info": win_info
    }

def restore_wechat_after_scan(lifecycle_meta: Optional[Dict[str, Any]] = None):
    """
    【微信无感生命周期守护：扫描后现场还原】
    - 若扫描前微信本来就未打开窗口（或处于隐藏/最小化），扫描完毕后自动将微信窗口隐藏归位 (Cmd+H / set visible false)；
    - 绝不调用 quit 强制退出（确保后台继续正常接收新消息与电话，且免除下次启动的扫码确认）；
    - 若扫描前微信原本就是打开的，绝对不碰窗口，原封不动保留用户的聊天界面。
    """
    if not lifecycle_meta:
        return
        
    was_window_open = lifecycle_meta.get("was_window_open", True)
    if not was_window_open:
        logger.info("微信主窗口为本次巡检临时静默唤起，正在执行无感现场隐藏归位...")
        try:
            script = 'tell application "System Events" to set visible of process "WeChat" to false'
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=2)
        except Exception as e:
            logger.warning(f"巡检后自动隐藏微信窗口异常: {e}")


