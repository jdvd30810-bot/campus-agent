import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger("campus-agent.groups")

GROUPS_FILE = Path(__file__).resolve().parent.parent / "monitored_groups.json"

DEFAULT_CONFIG = {
    "interval_minutes": 30,
    "last_inspected_at": None,
    "groups": [
        {"name": "2024级班级通知大群", "enabled": True},
        {"name": "高等数学课程答疑群", "enabled": True},
        {"name": "学院学生会官方群", "enabled": False}
    ]
}

def load_group_config() -> Dict[str, Any]:
    """读取监控群组配置"""
    if not GROUPS_FILE.exists():
        save_group_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
    try:
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取群组配置失败: {e}")
        return DEFAULT_CONFIG

def save_group_config(config: Dict[str, Any]):
    """保存监控群组配置"""
    try:
        with open(GROUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        logger.info("群组配置已保存。")
    except Exception as e:
        logger.error(f"保存群组配置失败: {e}")

def get_enabled_groups() -> List[str]:
    """获取所有已勾选启用的群组名称"""
    cfg = load_group_config()
    return [g["name"] for g in cfg.get("groups", []) if g.get("enabled")]

def get_group_info(group_name: str) -> Dict[str, Any]:
    """获取指定群的详细配置（可信发言人白名单、归属分类等）"""
    cfg = load_group_config()
    for g in cfg.get("groups", []):
        if g.get("name") == group_name:
            return g
    return {}

def get_trusted_speakers(group_name: str) -> List[str]:
    """获取该群的可信发言人名单（如：导师/辅导员/班干）"""
    info = get_group_info(group_name)
    speakers = info.get("trusted_speakers", [])
    if not speakers:
        # 通用兜底可信角色关键词
        return ["老师", "教师", "辅导员", "班长", "学委", "助教", "会长"]
    return speakers

def get_group_category(group_name: str) -> str:
    """根据群组特征或配置推断其默认分类：course / admin / activity"""
    info = get_group_info(group_name)
    if "category" in info:
        return info["category"]
    
    # 智能启发式分类
    name = group_name.lower()
    if any(k in name for k in ["英语", "代数", "数学", "计算机", "形策", "德法", "作业", "课", "大作业"]):
        return "course"
    elif any(k in name for k in ["通知", "班", "团", "辅导员", "学院", "年级", "综测"]):
        return "admin"
    elif any(k in name for k in ["会", "社团", "活动", "讲座", "协会", "志愿者"]):
        return "activity"
    return "course"

# ===== 迭代 2 扩展：微信群个性化画像规则与智能预设库 =====

DEFAULT_GROUP_RULE: Dict[str, Any] = {
    "filter_mode": "normal",  # "strict" (仅采纳置信发言人), "normal" (置信优先+高确信DDL), "loose" (全员潜在活动)
    "trusted_speakers": ["老师", "辅导员", "班长", "学委", "助教"],
    "keywords_whitelist": [],
    "keywords_blacklist": ["拼车", "外卖", "开黑", "兼职", "砍一刀", "互赞"],
    "require_confirm": False,
    "target_apple_list": "",
    "custom_notes": ""
}

RULE_PRESETS: Dict[str, Any] = {
    "course": {
        "id": "course",
        "name": "课程大作业模式",
        "category": "course",
        "icon": "🎓",
        "description": "专为专业课与公选课设计，重点提取作业实验报告与期末 DDL",
        "filter_mode": "normal",
        "trusted_speakers": ["任课老师", "主讲教师", "助教", "学委", "课代表"],
        "keywords_whitelist": ["大作业", "实验报告", "期末考试", "作业", "DDL", "截止", "代码提交", "雨课堂"],
        "keywords_blacklist": ["拼车", "点外卖", "开黑", "游戏", "兼职", "代拿快递", "互赞"],
        "require_confirm": False,
        "target_apple_list": "课程作业"
    },
    "admin": {
        "id": "admin",
        "name": "辅导员/班级通知模式",
        "category": "admin",
        "icon": "🏛️",
        "description": "重点关注年级事务、奖助学金、综测评定与放假调课，杜绝吹水干扰",
        "filter_mode": "strict",
        "trusted_speakers": ["辅导员", "班长", "团支书", "教学秘书", "教务处", "党支部书记"],
        "keywords_whitelist": ["通知", "填表", "签到", "综测", "奖学金", "放假", "调课", "问卷", "回执", "青年大学习"],
        "keywords_blacklist": ["拼车", "点外卖", "开黑", "王者荣耀", "求点赞", "二手闲置", "拼多多"],
        "require_confirm": False,
        "target_apple_list": "校园事务"
    },
    "activity": {
        "id": "activity",
        "name": "社团/学术讲座模式",
        "category": "activity",
        "icon": "🎭",
        "description": "自动抓取讲座打卡、第二课堂学分与比赛报名，生成日历事件",
        "filter_mode": "loose",
        "trusted_speakers": ["会长", "部长", "指导老师", "队长", "社长"],
        "keywords_whitelist": ["学术讲座", "第二课堂", "到梦空间", "学分", "招新", "志愿服务", "比赛报名"],
        "keywords_blacklist": ["游戏开黑", "砍一刀"],
        "require_confirm": True,
        "target_apple_list": "社团活动"
    },
    "dorm": {
        "id": "dorm",
        "name": "宿舍生活与安全模式",
        "category": "admin",
        "icon": "🛏️",
        "description": "实时关注查寝卫生、水电缴费、断电报修与寝室安全提醒",
        "filter_mode": "strict",
        "trusted_speakers": ["宿管", "宿管阿姨", "楼长", "楼栋管家", "自律会"],
        "keywords_whitelist": ["查寝", "卫生检查", "电费", "水费", "安全消杀", "断电", "关窗锁门", "违章电器"],
        "keywords_blacklist": ["外卖求带", "拼单", "借充电器"],
        "require_confirm": False,
        "target_apple_list": "宿舍生活"
    }
}

def get_rule_presets() -> Dict[str, Any]:
    """获取所有智能预设模板"""
    return RULE_PRESETS

def get_group_rule(group_name: str) -> Dict[str, Any]:
    """获取群组个性化画像规则，若未设置则智能填充默认值"""
    info = get_group_info(group_name)
    category = get_group_category(group_name)
    preset = RULE_PRESETS.get(category, RULE_PRESETS["course"])

    rule = {
        "name": group_name,
        "category": info.get("category", category),
        "filter_mode": info.get("filter_mode", preset["filter_mode"]),
        "trusted_speakers": info.get("trusted_speakers", preset["trusted_speakers"]),
        "keywords_whitelist": info.get("keywords_whitelist", preset["keywords_whitelist"]),
        "keywords_blacklist": info.get("keywords_blacklist", preset["keywords_blacklist"]),
        "require_confirm": info.get("require_confirm", preset.get("require_confirm", False)),
        "target_apple_list": info.get("target_apple_list", preset.get("target_apple_list", "")),
        "custom_notes": info.get("custom_notes", "")
    }
    return rule

def update_group_rule(group_name: str, rule_update: Dict[str, Any]) -> bool:
    """更新单个群组的画像与过滤规则"""
    cfg = load_group_config()
    found = False
    for g in cfg.get("groups", []):
        if g.get("name") == group_name:
            found = True
            for k in [
                "category", "filter_mode", "trusted_speakers",
                "keywords_whitelist", "keywords_blacklist",
                "require_confirm", "target_apple_list", "custom_notes"
            ]:
                if k in rule_update:
                    g[k] = rule_update[k]
            break
            
    if not found:
        # 新增群
        new_g = {"name": group_name, "enabled": True}
        for k in [
            "category", "filter_mode", "trusted_speakers",
            "keywords_whitelist", "keywords_blacklist",
            "require_confirm", "target_apple_list", "custom_notes"
        ]:
            if k in rule_update:
                new_g[k] = rule_update[k]
        cfg.setdefault("groups", []).append(new_g)

    save_group_config(cfg)
    logger.info(f"群组【{group_name}】规则已更新保存。")
    return True

def fast_filter_chat_text(group_name: str, text: str) -> Dict[str, Any]:
    """
    Stage 1 极速前置过滤：在发起 OCR 或大模型提取前，
    检查文本是否仅命中黑名单关键词且无任何置信发言人或白名单关键词。
    返回: {'should_skip': bool, 'reason': str}
    """
    rule = get_group_rule(group_name)
    trusted = rule.get("trusted_speakers", [])
    whitelist = rule.get("keywords_whitelist", [])
    blacklist = rule.get("keywords_blacklist", [])

    # 1. 检查是否出现可信发言人
    has_trusted = any(speaker in text for speaker in trusted if speaker)
    if has_trusted:
        return {"should_skip": False, "reason": "匹配到置信发言人白名单"}

    # 2. 检查是否出现关注白名单关键词
    has_whitelist = any(kw in text for kw in whitelist if kw)
    if has_whitelist:
        return {"should_skip": False, "reason": "匹配到关注白名单关键词"}

    # 3. 检查是否纯粹命中黑名单关键词
    has_blacklist = any(kw in text for kw in blacklist if kw)
    if has_blacklist:
        return {
            "should_skip": True,
            "reason": f"命中黑名单噪音关键词（如：{', '.join([k for k in blacklist if k in text][:3])}）且无置信发言人"
        }

    # 4. 严格模式 (strict) 下，若完全没有置信发言人且没有明确作业词，直接过滤
    if rule.get("filter_mode") == "strict":
        course_markers = ["作业", "实验", "考试", "通知", "填表", "截止", "ddl", "签到"]
        if not any(m in text.lower() for m in course_markers):
            return {
                "should_skip": True,
                "reason": "严格模式下未检测到置信发言人或核心通知标记"
            }

    return {"should_skip": False, "reason": "通过规则前置预检"}

