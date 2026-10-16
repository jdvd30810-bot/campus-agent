"""
Campus-Agent - 微信 4.x 本地数据库静默解密与监听引擎
---------------------------------------------------
功能：
在后台静默读取 Mac 本地 WeChat 4.x 数据库，实现：
1. 用户不需要打开微信群聊；
2. 即使群聊免打扰，也能实时捕获新消息；
3. 零界面干扰，不抢鼠标焦点，不弹窗口。
"""

import os
import json
import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("campus-agent.wechat_db")

WECHAT_CONTAINER = Path.home() / "Library/Containers/com.tencent.xinWeChat/Data/Documents/xwechat_files"
KEYS_FILE = Path(__file__).resolve().parent.parent / "wechat_keys.json"
DECRYPTED_DIR = Path(__file__).resolve().parent.parent / "decrypted_db"

def check_disk_access() -> bool:
    """检查终端是否具有『完全磁盘访问权限』"""
    if not WECHAT_CONTAINER.exists():
        return False
    try:
        # 尝试列出文件
        list(WECHAT_CONTAINER.iterdir())
        return True
    except PermissionError:
        return False

def find_wechat_accounts() -> List[Path]:
    """定位本机所有登录过的微信账户目录"""
    if not check_disk_access():
        return []
    accounts = []
    try:
        for item in WECHAT_CONTAINER.iterdir():
            # 过滤掉系统目录，找出真正的 wxid 目录
            if item.is_dir() and not item.name.startswith("."):
                db_dir = item / "db_storage"
                if db_dir.exists():
                    accounts.append(item)
    except Exception as e:
        logger.error(f"遍历微信目录异常: {e}")
    return accounts

def get_latest_messages_from_decrypted(db_path: Path, limit: int = 20) -> List[Dict[str, Any]]:
    """从解密后的标准 SQLite 数据库中读取最新群消息"""
    if not db_path.exists():
        return []
    messages = []
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 查询最近消息（表结构兼容 WeChat 4.x）
        cursor.execute("""
            SELECT message_id, talker, content, create_time 
            FROM message 
            ORDER BY create_time DESC 
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        for r in rows:
            messages.append(dict(r))
        conn.close()
    except Exception as e:
        logger.warning(f"读取解密数据库失败: {e}")
    return messages
