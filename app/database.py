import sqlite3
import logging
from datetime import datetime
from app.config import settings

logger = logging.getLogger("campus-agent.db")

def get_connection():
    """获取 SQLite 数据库连接"""
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """初始化数据库表结构"""
    logger.info(f"正在初始化 SQLite 数据库: {settings.DB_PATH}")
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. 令牌表 (用户权限)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                remark TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 2. 消息处理日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS process_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                source TEXT,
                raw_content TEXT,
                has_actionable_items INTEGER,
                summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. 视觉消息高水位线与指纹表 (Cutoff & Watermark Deduplication)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS visual_watermarks (
                group_name TEXT PRIMARY KEY,
                text_hash TEXT NOT NULL,
                last_extracted_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. 已同步待办与日历项存根与回读回执表 (Bi-directional Receipts & Idempotency)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS synced_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT,
                item_fingerprint TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                due_datetime TEXT,
                category TEXT DEFAULT 'course',
                apple_item_id TEXT,
                verified INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 预先插入配置中的合法令牌
        for token in settings.VALID_TOKENS:
            cursor.execute("""
                INSERT OR IGNORE INTO users (token, remark)
                VALUES (?, ?)
            """, (token, "初始默认用户"))
            
        conn.commit()
    logger.info("SQLite 数据库初始化完成！")

def verify_token(token: str) -> bool:
    """校验 Token 是否有效"""
    if token in settings.VALID_TOKENS:
        return True
    
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE token = ?", (token,))
        row = cursor.fetchone()
        return row is not None

def log_request(token: str, source: str, raw_content: str, has_actionable: bool, summary: str):
    """记录一次处理日志"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO process_logs (token, source, raw_content, has_actionable_items, summary)
                VALUES (?, ?, ?, ?, ?)
            """, (token, source, raw_content, 1 if has_actionable else 0, summary))
            conn.commit()
    except Exception as e:
        logger.warning(f"记录调用日志失败: {e}")

import hashlib

def compute_text_hash(text: str) -> str:
    """计算屏幕文本的 SHA256 视觉特征哈希"""
    clean = "".join(text.split())
    return hashlib.sha256(clean.encode("utf-8")).hexdigest()

def check_and_update_watermark(group_name: str, raw_text: str) -> tuple[bool, str]:
    """
    检查该群当前屏幕内容是否与上一次完全相同 (高水位线去重)
    返回: (is_changed: bool, current_hash: str)
    若 is_changed 为 False，表示内容完全没有新消息，可跳过 LLM 提取以节省 Token 与避免重复。
    """
    current_hash = compute_text_hash(raw_text)
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT text_hash FROM visual_watermarks WHERE group_name = ?", (group_name,))
            row = cursor.fetchone()
            if row and row["text_hash"] == current_hash:
                # 内容无变化
                return False, current_hash
            
            # 内容有变化或首次扫描，更新水位线
            cursor.execute("""
                INSERT INTO visual_watermarks (group_name, text_hash, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(group_name) DO UPDATE SET
                    text_hash = excluded.text_hash,
                    updated_at = CURRENT_TIMESTAMP
            """, (group_name, current_hash))
            conn.commit()
            return True, current_hash
    except Exception as e:
        logger.warning(f"高水位线检测异常: {e}")
        return True, current_hash

def compute_item_fingerprint(title: str, due_datetime: str, category: str = "course") -> str:
    """计算单个 DDL/待办项的唯一幂等指纹"""
    seed = f"{title.strip()}|{due_datetime or 'none'}|{category}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

def is_item_already_synced(fingerprint: str) -> bool:
    """判断该 DDL 是否之前已经写入过 Apple Reminders/Calendar"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM synced_items WHERE item_fingerprint = ?", (fingerprint,))
            return cursor.fetchone() is not None
    except Exception as e:
        logger.warning(f"查询待办幂等性失败: {e}")
        return False

def record_synced_item(
    group_name: str,
    fingerprint: str,
    title: str,
    due_datetime: str,
    category: str,
    apple_item_id: str = "",
    verified: bool = True
):
    """记录已成功写入并完成回读确认的待办项"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO synced_items 
                (group_name, item_fingerprint, title, due_datetime, category, apple_item_id, verified, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (group_name, fingerprint, title, due_datetime or "", category, apple_item_id or "", 1 if verified else 0))
            conn.commit()
    except Exception as e:
        logger.warning(f"记录已同步项失败: {e}")

def get_recent_synced_items(limit: int = 20) -> list[dict]:
    """获取最近成功写入且已验真的日程/待办列表"""
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, group_name, item_fingerprint, title, due_datetime, category, apple_item_id, verified, created_at
                FROM synced_items
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        logger.warning(f"获取已同步待办记录失败: {e}")
        return []

