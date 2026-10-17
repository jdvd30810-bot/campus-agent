from typing import List, Optional
from pydantic import BaseModel, Field

class ExtractRequest(BaseModel):
    """客户端提交的消息请求结构"""
    token: str = Field(..., description="用户的专属鉴权令牌，如 USER-888")
    content: str = Field(..., description="从群聊复制的原始文本内容")
    source: Optional[str] = Field("unknown", description="请求来源，例如 mac_clipboard 或 ios_shortcut")

class TodoItem(BaseModel):
    """结构化待办项"""
    title: str = Field("校园待办", description="待办简短标题，如'提交线性代数作业'")
    deadline: Optional[str] = Field(None, description="时间节点/截止时间 DDL，如'本周五23:59前'")
    due_datetime: Optional[str] = Field(None, description="标准的日期时间字符串，格式为 'YYYY-MM-DD HH:MM:SS'，用于直接写入系统提醒事项闹钟")
    location: Optional[str] = Field(None, description="提交地点或平台，如'雨课堂 / 教学楼302'")
    priority: str = Field("HIGH", description="优先级：HIGH(高优待办) / NORMAL(普通待办)")
    action_item: str = Field("", description="具体需要完成的行动描述")
    is_calendar_event: bool = Field(False, description="是否是具体时间段活动（如开会、讲座、考试），适合写入日历")
    category: str = Field("course", description="待办分类：course(课程作业/考试) | admin(班级行政/问卷/事务) | activity(社团活动/讲座/日常)")
    speaker: Optional[str] = Field(None, description="发布者姓名或头衔，如'主讲老师'、'班长'")
    is_trusted_speaker: bool = Field(False, description="是否经过群置信发言人白名单验证")
    source_group: Optional[str] = Field(None, description="来源群聊名称")
    confidence: float = Field(0.95, description="置信度打分 (0.0 - 1.0)")
    need_human_confirm: bool = Field(False, description="低置信度或模糊时间时标记为需要人工复核")
    item_fingerprint: Optional[str] = Field(None, description="任务唯一特征指纹(SHA256)")
    receipt: Optional[dict] = Field(None, description="Apple 系统回读验证回执")

class NotificationItem(BaseModel):
    """结构化通知项"""
    title: str = Field("校园通知", description="通知标题")
    importance: str = Field("NORMAL", description="重要级别：HIGH(重要通知) / NORMAL(普通通知)")
    summary: str = Field("", description="提炼后的核心通知摘要")
    category: str = Field("admin", description="通知分类：course | admin | activity")
    speaker: Optional[str] = Field(None, description="发布者姓名或头衔")

class ExtractResponse(BaseModel):
    """返回给客户端的标准结构"""
    status: str = Field("success", description="处理状态：success / error")
    message: str = Field("", description="提示信息")
    has_actionable_items: bool = Field(False, description="是否包含有效待办或重要通知")
    is_watermark_unchanged: bool = Field(False, description="是否命中高水位线去重(屏幕文本无变化)")
    todos: List[TodoItem] = Field(default_factory=list, description="提取出的待办列表")
    notifications: List[NotificationItem] = Field(default_factory=list, description="提取出的重要通知")
    formatted_markdown: str = Field("", description="排版整理后的文本，方便快捷指令或弹窗直接展示")


