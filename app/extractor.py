import json
import logging
from datetime import datetime
from typing import Dict, Any
from openai import OpenAI
from app.config import settings
from app.schemas import ExtractResponse, TodoItem, NotificationItem

logger = logging.getLogger("campus-agent.extractor")

from app.database import compute_item_fingerprint
from app.groups_manager import get_group_rule, fast_filter_chat_text

SYSTEM_PROMPT = """你是一个专门为中国大学生打造的校园消息聚合与待办提取助手「Campus-Agent」。
用户的输入通常是从微信群、QQ群复制出来的嘈杂聊天记录。

你的核心任务：
1. 过滤一切废话（如纯刷屏的"收到"、"好的"、"+1"、表情符号、无关闲聊）。
2. 识别并提取核心待办（需学生行动的事项，如提交作业、填写问卷、抢课、开会、考试等），提取时间节点（DDL）、地点/提交渠道。
3. 识别并提取重要通知（不一定需要行动，但重要的政策、放假通知、调课信息等）。
4. 时间标准化解析（重要！）：结合用户给出的基准当前时间，将相对时间（如"本周五下午5点"、"明天上午10:00"、"10月17日23:59"）严格换算推导为标准日期时间格式 due_datetime: 'YYYY-MM-DD HH:MM:SS'。若无法确定具体年份按当前年份推算，若没有具体时间可设为当天 23:59:00。
5. 细粒度三维分类（category）：
   - "course": 课程作业、实验报告、随堂测验、期末考试、大作业、打卡练习
   - "admin": 班级团支部通知、学院行政、综测评奖、问卷调查、宿舍检查、放假调课
   - "activity": 俱乐部纳新、学术讲座、志愿活动、文艺体育、宣讲会
6. 发言人画像识别（speaker profiling）：
   - 提取该消息的发送人昵称或身份（如"教师 谢雨岑"、"辅导员"、"班长"）。
   - 如果发送人属于用户指定的「可信发言人白名单」或具有明显官方教师/辅导员特征，将 is_trusted_speaker 设为 true，并赋予 priority: "HIGH"。
7. 区分类型：如果是固定时段参加的活动（讲座、开会、考试），设置 is_calendar_event: true；如果是截止提交某物的 DDL（交作业、填表），设置 is_calendar_event: false。
8. 如果消息里没有任何有效信息（全是闲聊或收到），将 has_actionable_items 设为 false。

你必须严格以合法的 JSON 格式返回，JSON 结构如下：
{
  "has_actionable_items": true,
  "todos": [
    {
      "title": "简明标题",
      "deadline": "原始文本中的截止时间描述，如：周五17:00前",
      "due_datetime": "推算后的标准时间，如：2026-10-17 17:00:00 (若无明确时间则为 null)",
      "location": "提交渠道或地点，如：雨课堂/教学楼401",
      "priority": "HIGH",
      "action_item": "具体要做的事情详情",
      "is_calendar_event": false,
      "category": "course",
      "speaker": "发布人姓名或头衔，如'教师 谢雨岑'",
      "is_trusted_speaker": true
    }
  ],
  "notifications": [
    {
      "title": "通知主题",
      "importance": "HIGH",
      "summary": "提炼后的通知要点",
      "category": "admin",
      "speaker": "发布人姓名或头衔"
    }
  ],
  "formatted_markdown": "排版好的展示文本"
}

关于 formatted_markdown 的格式规范（务必清晰易读，适合手机弹窗或提醒）：
- 按照分类展示：课程作业【📚】、班级行政【🏛️】、社团日常【🎭】。
- 列出：标题、⏰时间、📍地点、👤发布人（若为置信教师标明✨权威）、📌要求。
- 如果全是闲聊，输出：'🟢 无需处理：本段内容为日常闲聊或刷屏信息。'
"""

def extract_campus_info(
    raw_text: str,
    group_name: str = "默认会话",
    trusted_speakers: list = None
) -> ExtractResponse:
    """
    调用大模型提取聊天记录中的待办和通知，支持分类学、群个性化规则过滤、发言人白名单与特征指纹计算
    """
    # 0. 载入该群个性化画像规则
    group_rule = get_group_rule(group_name) if group_name else {}
    if not trusted_speakers:
        trusted_speakers = group_rule.get("trusted_speakers", ["老师", "辅导员", "班长", "助教"])

    # 1. Stage 1 本地黑名单极速过滤 (0ms 拦截纯噪音)
    if group_name and group_name not in ["默认会话", "当前活跃微信群"]:
        fast_res = fast_filter_chat_text(group_name, raw_text)
        if fast_res.get("should_skip"):
            logger.info(f"🚫 [规则前置拦截] 群【{group_name}】: {fast_res['reason']}")
            return ExtractResponse(
                status="success",
                message=f"已由群规则前置过滤: {fast_res['reason']}",
                has_actionable_items=False,
                todos=[],
                notifications=[],
                formatted_markdown=f"🟢 **无需处理**：根据群【{group_name}】的个性化过滤偏好，{fast_res['reason']}。"
            )

    # 检查是否配置了 API Key
    if not settings.LLM_API_KEY or settings.LLM_API_KEY == "your_api_key_here":
        logger.warning("未检测到有效 LLM_API_KEY，返回模拟/配置引导响应。")
        mock_md = (
            "⚠️ 【提示：尚未配置 API 密钥】\n\n"
            "系统已成功收到消息，但尚未配置有效的 LLM_API_KEY。\n"
            "请在项目根目录的 `.env` 文件中填入你的 API Key 后重试。\n\n"
            f"原始消息预览：\n> {raw_text[:80]}..."
        )
        return ExtractResponse(
            status="success",
            message="未配置真实 LLM_API_KEY，已触发配置引导模式",
            has_actionable_items=False,
            todos=[],
            notifications=[],
            formatted_markdown=mock_md
        )

    client = OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=20.0,
        max_retries=1
    )

    logger.info(f"正在调用大模型 ({settings.LLM_MODEL}) 处理消息，群名: 【{group_name}】，长度: {len(raw_text)} 字符...")

    content = ""
    try:
        now_anchor = datetime.now().strftime("%Y年%m月%d日 %H:%M:%S 星期%w")
        rule_hints = [
            f"【当前系统基准时间：{now_anchor}】",
            f"【群组名】：{group_name}",
            f"【过滤严格度】：{group_rule.get('filter_mode', 'normal')}",
            f"【可信官方发言人白名单】：{', '.join(trusted_speakers)}"
        ]
        if group_rule.get("keywords_whitelist"):
            rule_hints.append(f"【优先关注关键词】：{', '.join(group_rule['keywords_whitelist'])}")
        if group_rule.get("keywords_blacklist"):
            rule_hints.append(f"【噪音屏蔽关键词】：{', '.join(group_rule['keywords_blacklist'])}")
        if group_rule.get("custom_notes"):
            rule_hints.append(f"【该群特别提示】：{group_rule['custom_notes']}")

        prompt_with_time = "\n".join(rule_hints) + f"\n\n请分析以下群聊内容：\n\n{raw_text}"

        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt_with_time}
            ],
            response_format={"type": "json_object"},
            temperature=0.2
        )

        content = response.choices[0].message.content
        logger.info("大模型响应成功，开始解析 JSON 数据...")
        data = json.loads(content)

        todos = []
        for item in data.get("todos", []):
            todo = TodoItem(**item)
            todo.source_group = group_name
            # 根据群规则注入人工确认标记
            if group_rule.get("require_confirm"):
                todo.need_human_confirm = True
            # 计算唯一任务特征指纹，用于幂等去重
            todo.item_fingerprint = compute_item_fingerprint(todo.title, todo.due_datetime, todo.category)
            todos.append(todo)

        notifications = [NotificationItem(**item) for item in data.get("notifications", [])]
        has_items = data.get("has_actionable_items", bool(todos or notifications))
        markdown = data.get("formatted_markdown", "未生成格式化文本")

        logger.info(f"解析完成！提取到 {len(todos)} 项待办，{len(notifications)} 项通知。")
        return ExtractResponse(
            status="success",
            message="提取成功",
            has_actionable_items=has_items,
            todos=todos,
            notifications=notifications,
            formatted_markdown=markdown
        )

    except json.JSONDecodeError as jde:
        logger.error(f"大模型返回的不是合法 JSON: {jde}")
        fallback_md = f"🚨 【待办提取】\n(模型未输出规范结构，原始回答摘录):\n{content[:200]}"
        return ExtractResponse(
            status="success",
            message="解析部分完成",
            has_actionable_items=True,
            formatted_markdown=fallback_md
        )
    except Exception as e:
        logger.error(f"调用大模型异常: {e}", exc_info=True)
        return ExtractResponse(
            status="error",
            message=f"调用模型失败: {str(e)}",
            has_actionable_items=False,
            formatted_markdown=f"❌ 处理失败：{str(e)}"
        )
