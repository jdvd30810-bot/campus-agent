import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("campus-agent.voice")

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "app" / "static" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

NAILONG_VOICE_DESIGN_SPEC = {}
PRESET_AUDIO_CLIPS = {}

def clean_speech_text(text: str) -> str:
    """清理文本为纯文本"""
    if not text:
        return ""
    return text.replace("#", "").replace("*", "").replace("`", "").strip()

def play_audio_on_mac(audio_path_or_url: str):
    """【用户已停用】彻底停用所有 macOS 原生音频播放，保持 100% 静音"""
    logger.debug("音频播放已全量停用 (Muted)")
    return None

def synthesize_nailong_speech(text: str, play_on_mac: bool = False) -> Optional[str]:
    """【用户已停用】彻底停用所有语音合成与口播输出"""
    logger.debug("语音合成引擎已全量停用 (Muted)")
    return None

def get_nailong_preset_audio(event_type: str) -> str:
    """【用户已停用】返回空"""
    return ""
