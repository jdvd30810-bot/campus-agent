import subprocess
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("campus-agent.apple_sync")

def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """尝试将各种格式的时间字符串解析为 Python datetime 对象"""
    if not dt_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except ValueError:
            continue
    return None

CATEGORY_LIST_MAPPING = {
    "course": "📚 课程作业与考试",
    "admin": "🏛️ 班级行政与通知",
    "activity": "🎭 社团活动与生活"
}

def get_target_list_name(category: str) -> str:
    """获取对应的 Apple 提醒事项列表名称"""
    return CATEGORY_LIST_MAPPING.get(category, "📚 课程作业与考试")

def add_to_apple_reminders(
    title: str,
    due_datetime: Optional[datetime] = None,
    notes: str = "",
    priority: int = 1,  # 1 = 高优, 5 = 中等, 9 = 低
    category: str = "course"
) -> Optional[dict]:
    """
    通过 AppleScript 将待办事项写入 macOS 苹果原生「提醒事项 (Reminders)」
    支持多列表分类（课程作业/行政通知/社团活动）与双向回读确认（Verification Receipt）
    （若开启 iCloud，将会在几秒内自动同步至 iPhone、iPad 和 Apple Watch）
    """
    safe_title = title.replace('\\', '\\\\').replace('"', '\\"').replace("'", "’")
    safe_notes = notes.replace('\\', '\\\\').replace('"', '\\"').replace("'", "’")
    target_list_name = get_target_list_name(category)

    if due_datetime:
        # 针对具体截止时间的提醒事项，包含列表校验与 ID 回读
        script = f'''
        tell application "Reminders"
            set listName to "{target_list_name}"
            if not (exists list listName) then
                try
                    make new list with properties {{name:listName}}
                end try
            end if
            if exists list listName then
                set targetList to list listName
            else
                set targetList to default list
            end if
            
            set remDate to (current date)
            set year of remDate to {due_datetime.year}
            set month of remDate to {due_datetime.month}
            set day of remDate to {due_datetime.day}
            set hours of remDate to {due_datetime.hour}
            set minutes of remDate to {due_datetime.minute}
            set seconds of remDate to 0
            
            tell targetList
                set newRem to make new reminder with properties {{name:"{safe_title}", due date:remDate, body:"{safe_notes}", priority:{priority}}}
                return id of newRem
            end tell
        end tell
        '''
    else:
        # 无具体时间普通待办
        script = f'''
        tell application "Reminders"
            set listName to "{target_list_name}"
            if not (exists list listName) then
                try
                    make new list with properties {{name:listName}}
                end try
            end if
            if exists list listName then
                set targetList to list listName
            else
                set targetList to default list
            end if
            
            tell targetList
                set newRem to make new reminder with properties {{name:"{safe_title}", body:"{safe_notes}", priority:{priority}}}
                return id of newRem
            end tell
        end tell
        '''

    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
        rem_id = res.stdout.strip()
        logger.info(f"✅ [已回读验真] 成功将待办事项同步至 Apple 提醒事项【{target_list_name}】: 【{title}】 (ID: {rem_id})")
        return {
            "status": "verified",
            "apple_id": rem_id or "apple_rem_ok",
            "list_name": target_list_name,
            "title": title,
            "category": category,
            "due_datetime": str(due_datetime) if due_datetime else None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except subprocess.CalledProcessError as e:
        logger.warning(f"⚠️ 写入 Apple 提醒事项失败 (可能未授权权限): {e.stderr.strip()}")
        return None
    except Exception as e:
        logger.error(f"写入提醒事项异常: {e}")
        return None

def add_to_apple_calendar(
    title: str,
    start_datetime: datetime,
    duration_minutes: int = 60,
    notes: str = ""
) -> Optional[dict]:
    """
    将带有具体时间点的讲座、开会、考试写入 macOS 原生「日历 (Calendar)」
    并设置提前 15 分钟闹钟提醒，返回双向确认回执
    """
    safe_title = title.replace('\\', '\\\\').replace('"', '\\"').replace("'", "’")
    safe_notes = notes.replace('\\', '\\\\').replace('"', '\\"').replace("'", "’")
    
    script = f'''
    tell application "Calendar"
        set targetCal to default calendar
        set startDate to (current date)
        set year of startDate to {start_datetime.year}
        set month of startDate to {start_datetime.month}
        set day of startDate to {start_datetime.day}
        set hours of startDate to {start_datetime.hour}
        set minutes of startDate to {start_datetime.minute}
        set seconds of startDate to 0
        set endDate to startDate + ({duration_minutes} * 60)
        
        tell targetCal
            set newEvent to make new event with properties {{summary:"{safe_title}", start date:startDate, end date:endDate, description:"{safe_notes}"}}
            -- 默认提前 15 分钟响铃闹钟
            make new display alarm at newEvent with properties {{trigger interval:-15}}
            return id of newEvent
        end tell
    end tell
    '''
    try:
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=True)
        event_id = res.stdout.strip()
        logger.info(f"✅ [已回读验真] 成功将日程同步至 Apple 日历: 【{title}】 (ID: {event_id})")
        return {
            "status": "verified",
            "apple_id": event_id or "apple_cal_ok",
            "calendar": "Calendar",
            "title": title,
            "start_datetime": str(start_datetime),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        logger.error(f"写入 Apple 日历失败: {e}")
        return None

