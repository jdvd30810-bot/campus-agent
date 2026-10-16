import os
from pathlib import Path
from dotenv import load_dotenv

# 找到项目根目录下的 .env 文件
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

# 加载 .env 环境变量
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

class Settings:
    """系统配置读取类"""
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
    
    # 允许的 Token 列表（用逗号隔开）
    _tokens_raw: str = os.getenv("VALID_TOKENS", "USER-888,CAMPUS-TEST-001")
    VALID_TOKENS: set = {t.strip() for t in _tokens_raw.split(",") if t.strip()}
    
    # 数据库路径
    DB_PATH: Path = BASE_DIR / "campus_agent.db"

settings = Settings()
