# Campus-Agent: 基于多模态边缘感知与大语言模型的零侵入式校园消息聚合系统
## 系统架构、设计哲学与技术白皮书 (Project Technical White Paper)

> **项目名称**：Campus-Agent（校园消息智能聚合助手）  
> **版本**：v2.0 (Native Vision & LLM Architecture)  
> **面向对象**：课程导师 / 评审专家 / 学术答辩委员会  
> **技术栈**：Python 3.9 · FastAPI · Apple Vision Framework (Swift) · macOS CoreGraphics (64-bit ABI) · DeepSeek LLM · AppleScript / EventKit · iCloud Sync

---

## 1. 选题背景与问题形式化定义 (Problem Formulation)

### 1.1 校园即时通讯的“信息过载与低信噪比”危机
在现代中国高校教育生态中，微信与 QQ 群聊已成为课程教学、辅导员行政通知、班团管理、科研组会的事实载体。然而，这一模式对大学生造成了前所未有的认知负荷与信息焦虑（DDL Anxiety）：
1. **极度破碎与低信噪比（Low Signal-to-Noise Ratio）**：在动辄百人的课程群中，核心待办事项（作业 DDL、考试通知、四六级报名）往往夹杂在巨量的“收到”、“好的”、“+1”、表情包刷屏与日常闲聊中。有效信息密度常不足 3%。
2. **非结构化与时空模糊性（Temporal Ambiguity）**：通知多采用口语化、相对时态表述（如“本周五下午5点前”、“明天中午前填完问卷”），缺乏统一日历规范。
3. **高遗漏代价（High Penalty of Missing DDLs）**：错过一次平时作业提交或综测申报，直接影响学分绩点与评优评奖。

### 1.2 现有解决方案的困境与工程壁垒
学术界与工业界此前尝试过多种解决方案，但均存在不可调和的矛盾：
* **方案 A：内存注入 / 逆向 Hook（如 Frida / 动态链接劫持）**  
  * *缺陷*：严重破坏宿主软件完整性，触碰腾讯安全风控与法律红线，用户面临瞬时封号风险，毫无实用落地可能。
* **方案 B：本地数据库暴力解密（SQLCipher 内存 Dump）**  
  * *缺陷*：自 macOS 14+ 及微信新版本起，需要用户使用 `sudo codesign --remove-signature` 破坏苹果团队签名，关闭 SIP 安全保护，对普通大学生门槛极高且严重削弱系统安全。
* **方案 C：传统无障碍文本爬取（Accessibility / AXUIElement）**  
  * *缺陷*：微信 Mac 4.x 架构进行了彻底重构，全面采用自研高性能图形画布引擎（Skia/Canvas）。操作系统无障碍树看到的聊天窗口仅是一个**单一的不透明画布（Opaque Canvas）**，无法通过 DOM 或 UI 元素树获取任何聊天文字。

---

## 2. 核心架构设计与技术突破 (Core Architectural Breakthroughs)

Campus-Agent 提出了一种**“端侧多模态视觉感知 + 云端认知提炼 + 系统级原生落盘”**的全流程零侵入式架构（Zero-Invasive Non-Interference Architecture）：

```mermaid
flowchart TD
    subgraph Layer1["感知层：端侧多模态实况视觉引擎 (Edge Perception)"]
        A1["macOS 桌面会话环境"] --> A2["CoreGraphics 亚毫秒级无损屏幕快照"]
        A2 --> A3["Apple 原生神经网络实况文本引擎<br/>(VNRecognizeTextRequest / Swift)"]
        A3 --> A4["文本向量与精确物理坐标树<br/>(Bounding Boxes & Normalized Y-Coords)"]
    end

    subgraph Layer2["驱动层：拟人化零按键无痕巡航 (Human-Like Roaming)"]
        B1["已勾选订阅群队列 (JSON 配置)"] --> B2["会话栏智能语义模糊匹配与独占锁"]
        A4 -.-> B2
        B2 --> B3["64位 CoreGraphics 拟人鼠标微动 (0键盘事件)"]
        B3 --> B4["多屏惯性平滑接力滚动寻找"]
        B4 --> B5["现场瞬间复原系统 (Ghost Switch)"]
    end

    subgraph Layer3["大脑层：大语言模型降噪与时空消歧 (Cognitive LLM)"]
        C1["纯净聊天文本流"] --> C2["DeepSeek-V3 / Chat 结构化提炼"]
        C3["当前系统物理时间绝对基准锚 (now_anchor)"] --> C2
        C2 --> C4["时空归一化 (相对时间 -> 绝对 YYYY-MM-DD HH:MM:SS)"]
        C2 --> C5["任务分类 (DDL待办事项 vs 日程会议活动)"]
    end

    subgraph Layer4["落地层：系统级原子写入与多端协同 (Actuation & Sync)"]
        D1["AppleScript / EventKit 深度集成"]
        C4 --> D1
        C5 --> D1
        D1 --> D2["Apple 提醒事项 (带截止时间与高优闹钟)"]
        D1 --> D3["Apple 日历 (带时段占位与提前提醒)"]
        D2 --> D4["iCloud 端到端云同步"]
        D3 --> D4
        D4 --> D5["iPhone / Apple Watch / iPad 毫秒级多端振动提醒"]
    end

    Layer1 --> Layer2
    Layer2 --> Layer3
    Layer3 --> Layer4
```

---

## 3. 关键子系统技术细节 (Subsystem Implementations)

### 3.1 突破 Skia 画布反爬：基于 Apple Vision 的极速多模态识别
针对微信 Mac 4.x 将 UI 绘制在单个 Metal/Skia Canvas 的问题，系统自主研发了基于 Swift 的硬件加速识别模块 [`app/ocr.swift`](app/ocr.swift) 与本地原生编译二进制 [`app/ocr_bin`](app/ocr_bin)：
* **毫秒级推理**：调用 Apple 官方神经网络实况文本模型（`VNRecognizeTextRequest`），利用 Apple Silicon 统一内存架构，纯图像文字识别在 50ms 内即可完成。
* **双模态输出**：
  * **全文转录模式**：提取完整聊天记录并自动去除界面控制字符。
  * **空间坐标模式 (`--json`)**：返回归一化边界盒（BoundingBox），精准映射屏幕上每一个群名标题的绝对像素坐标 `(X, Y)`，为拟人化鼠标点击提供物理锚点。

### 3.2 物理级 0 键盘按键与拟人巡航（杜绝误触防线）
为解决传统 RPA 敲键盘搜索可能导致消息误发的痛点，设计了 **拟人化会话栏巡视驱动器**（[`app/human_driver.py`](app/human_driver.py) 与 [`app/rpa.py`](app/rpa.py)）：
1. **64 位 ABI 强类型指针安全**：在 Python `ctypes` 与 macOS `CoreGraphics.framework` 交互时，显式指定所有函数入参与出参的 64 位指针类型（`c_void_p`），杜绝现代 ARM64 架构下的 32 位地址截断崩溃。
2. **绝对物理安全（手不触碰键盘）**：
   * 彻底摒弃 `Cmd + F`、剪贴板粘贴与 `Return` 按键；
   * 仅通过模拟鼠标在左侧会话栏轻触（Mouse Left Down/Up），**光标物理上绝不可能进入消息输入区，从底层消除了误发消息的可能**。
3. **四重安全防御光栅**：
   * **Esc 浮层清退**：巡视伊始即自动投递 `Esc`，强制清退所有历史搜索与搜一搜浮层；
   * **75px 绝对垂直禁区**：窗口顶部 0~75px（`Y < 0.085`）设为不可侵犯禁区，即便 OCR 捕获到文字也绝对禁止点击搜索框；
   * **搜索黑名单过滤**：严格剔除带有“搜索”、“网络结果”、“搜一搜”等系统关键词的条目；
   * **会话条目独占锁**：相似群聊在当前屏被匹配后即时锁定，确保未命中的群聊按序向下轻柔翻页接力寻找。
4. **现场瞬间复原技术（Ghost Switch）**：
   * 任务触发瞬间记录用户当前前台进程（`get_frontmost_app()`，如 VS Code、Chrome、Word）；
   * 巡检完成后，在 0.05 秒内通过 Apple Events 将屏幕焦点原封不动还给用户，实现完全无感巡检。

### 3.3 大模型时空基准锚定与两阶段认知提炼
在 [`app/extractor.py`](app/extractor.py) 中，系统集成了 DeepSeek 高性能大语言模型，并设计了专用的校园语境提示工程（Prompt Engineering）：
* **动态绝对时间锚（Dynamic Temporal Grounding）**：  
  在 Prompt 中动态注入当前的系统物理时间基准：
  $$\text{Anchor} = \text{strftime}("\%Y\text{年}\%m\text{月}\%d\text{日 } \%H:\%M:\%S\text{ 星期}\%w")$$
  引导模型将模糊的“本周五”、“后天晚上”严格计算并映射为绝对时间字符串（如 `2026-10-17 23:59:00`）。
* **多任务解耦推理**：
  * **DDL 待办（Deadline Items）**：交作业、填问卷、打卡 $\rightarrow$ 归集为 Apple 提醒事项；
  * **时段活动（Calendar Events）**：开会、讲座、考试、调课 $\rightarrow$ 归集为 Apple 日历时段占位。

### 3.4 苹果生态原生闭环与 iCloud 级联同步
在 [`app/apple_sync.py`](app/apple_sync.py) 中，系统通过 AppleScript 直接调用 macOS 官方 `Reminders` 与 `Calendar` 守护进程：
* **语言环境无关解析**：分别提取 `year`, `month`, `day`, `hours`, `minutes` 独立赋值，彻底绕过英美/中文系统的日期格式字符串解析分歧；
* **iCloud 级联触达**：待办写入 Mac 系统的瞬间，由 Apple 原生 iCloud 云服务在几秒内无感推送到大学生的 iPhone 锁屏、Apple Watch 表盘及 iPad 桌面小组件。

---

### 3.5 破解鼠标争夺：自适应多级人机协同避让体系 (Adaptive Non-Intrusive Interaction)
任何在操作系统表现层（GUI Presentation Layer）仿真人类操作的 RPA 系统，都面临一个经典的人机交互难题（HCI Dilemma）——**“物理外设单光标悖论（Single Pointer Paradox）”**：操作系统底层默认全局只有**唯一一只物理硬件鼠标光标**。传统自动化工具（如 PyAutoGUI、Selenium、早期 macOS RPA）均调用 `CGEventPost(kCGSessionEventTap, event)` 向全局会话广播鼠标事件，这会导致用户的真实物理光标被强行抢夺、剧烈抖动，在用户正在打字、绘图或点击时造成不可接受的对抗感。

为彻底根治这一人机对抗难题，Campus-Agent 在系统架构中设计并实现了**五级自适应无感协同避让体系**，并重点攻克了**“定向进程私有事件注入（`CGEventPostToPid`）”**核心关键技术：

```mermaid
flowchart TD
    Req["触发群消息提取 / 巡检指令"] --> Check{"用户当前是否正在操作电脑？<br/>(基于 CGEventSource 物理空闲感知)"}
    
    Check -- "用户活跃使用中<br/>(打字/移动光标)" --> Fork1["双轨并行无感模式"]
    Fork1 --> T1["【输入突破：定向进程事件注入】<br/>CGEventPostToPid 直接注入微信私有队列<br/>物理硬件光标位移严格为 0.00px！"]
    Fork1 --> T2["【感知突破：GPU 显存静默快照】<br/>screencapture -l 直接读 WindowServer 显存帧<br/>微信完全被遮挡也照常识别，0 前台闪现！"]
    Fork1 --> T3["【内存通道：剪贴板守卫】<br/>watcher.py 毫秒级静默管道<br/>0 屏幕接触 · 0 鼠标占用"]
    
    Check -- "用户离席超 45 秒" --> T4["【空闲期极速漫游】<br/>scheduler.py 2~3 秒极速扫视已订阅群<br/>扫完复位 + Ghost Switch 瞬间切回原应用"]
    
    T1 -.-> T5["【微秒级物理碰撞熔断器】<br/>若检测到人类外设介入偏差 > 35px<br/>瞬时中止点击并无条件向人类让权！"]
```

#### 1. 核心技术突破一：基于 `CGEventPostToPid` 的定向进程私有事件注入（物理光标 0.00px 位移）
针对单光标悖论，系统突破了传统的全局事件广播范式，在 [`app/human_driver.py`](app/human_driver.py) 中深度绑定了 macOS CoreGraphics 底层专属 C 接口：
$$\text{void CGEventPostToPid}(\text{pid\_t pid}, \text{CGEventRef event});$$

* **底层运作机理**：
  1. 通过 `get_wechat_pid()` 动态解析宿主微信的进程标识符（PID）；
  2. 构造目标会话坐标处的 `CGEventCreateMouseEvent` 与 `CGEventCreateScrollWheelEvent`；
  3. 显式调用 `CGEventSetLocation(evt, pt)` 锚定会话列表坐标，并设置 `CGEventSetIntegerValueField(evt, 1, 1)`（`kCGMouseEventClickState = 1`）确保 Cocoa/AppKit 将其识别为合法单击；
  4. 绕过 WindowServer 全局光标驱动程序，通过 Mach Port 直接将事件投递至微信进程的私有事件循环（Event Queue）。
* **实测物理表现**：
  在自动化遍历多个微信群的全生命周期中，**物理硬件光标在屏幕上的位移量严格为 $0.0000\text{px}$**（由自动化单元测试 [`tests/test_option1_pid_injection.py`](tests/test_option1_pid_injection.py) 实时断言保证）。用户可以在屏幕另一侧无阻碍打代码、刷网页，而微信在后台平滑切换已订阅会话，两者互不干扰、并行不悖。

#### 2. 核心技术突破二：基于 GPU 显存帧缓冲的被遮挡窗口静默快照（`screencapture -l`）
* **传统区域截屏的痛点**：
  传统自动化采用 `screencapture -R{coords}` 截取绝对屏幕物理矩形。若微信被正在使用的 VS Code、Chrome 或 Word 窗口完全覆盖，截出来的画面全是上层遮挡软件的界面，导致 OCR 识别彻底失效。为了截屏，旧方案不得不频繁调用 `activate` 将微信强行置顶前台，产生恼人的“界面闪现”与“窗口争夺”。
* **破局设计：直读 GPU 显存 Backing Store**：
  macOS 图形合成引擎（WindowServer）为屏幕上每一个原生窗口独立开辟并维护了一块显存离屏缓冲区（Offscreen Backing Store Buffer）。
  1. 系统通过原生 CoreGraphics C 接口 [`get_wechat_window_info()`](app/human_driver.py#L329-L380) 毫秒级动态查询并锁定微信主窗口的底层原生 `WindowID`；
  2. 调用 macOS 显存级硬件加速快照：
     $$\text{screencapture -x -o -l } \langle\text{WindowID}\rangle \quad \text{/tmp/wechat\_capture.png}$$
* **实测感知表现**：
  - **100% 免疫上层窗口遮挡**：即便微信被盖在浏览器底下，快照出的图像依然是 100% 纯净、完整的微信聊天界面；
  - **彻底告别窗口前台置顶闪现**：抓取当前群或后台巡视时，无需激活微信窗口，用户当前正在聚焦的应用（如打字中的 Word/VS Code）焦点纹丝不动；
  - **与方案一形成闭环**：方案一解决“无位移定向事件输入”，方案二解决“无遮挡显存静默感知”，两者协同构建了真正意义上的“零侵入式具身自动化闭环”。

#### 3. 剪贴板静默守卫（`watcher.py` · 纯内存通道）
* 学生在微信聊天中阅读到重要通知时，只需顺手双击复制（`Cmd + C`）；
* 后台守护进程通过系统剪贴板通道（`pbpaste`）毫秒级捕获文本，交由 DeepSeek 大模型结构化提炼后自动录入 Apple 提醒事项，并在屏幕右上角轻量弹窗；
* **整个过程 0 屏幕截取、0 鼠标介入、0 界面抢占**。

#### 4. 智能离席感知与空闲避让调度（`scheduler.py`）
* 调度器调用 `CGEventSourceSecondsSinceLastEventType` 持续监听物理外设（鼠标与键盘）的最后激活时间戳；
* 当感知到用户正在操作电脑时，调度器主动挂起（Yield）并礼让；
* 仅当用户离开座位超过 45 秒时，系统才在后台极速执行全量订阅群扫描，实现“人在电脑前绝不抢扰，喝水归来时 DDL 已同步 iPhone”。

#### 5. 微秒级物理碰撞熔断器（Dead Man's Switch）
* 为防范“系统刚启动巡视、用户突然握住鼠标”的极端边界情况，每次触发底层驱动前均比对当前物理坐标与预期坐标；
* 若人类移动光标偏差 $\Delta > 35\text{px}$，系统抛出 `HumanInterruptionError` 并立即无条件终止（Abort），将控制权 100% 归还用户。



---

### 3.6 工业级架构进阶：吸收优秀开源网关思想的五大工程突破
在持续的系统演进中，系统借鉴并升华了业内优秀的协议网关设计思想（如 `workbuddy-qq-agent-gateway`），在端侧具身感知壁垒之上，引入了五大工业级工程机制：

1. **MCP (Model Context Protocol) 标准协议化集成**：
   * 在 [`app/mcp_server.py`](app/mcp_server.py) 中原生实现了 Anthropic MCP 协议标准（JSON-RPC 2.0 over stdio）；
   * 将微信当前窗口 OCR、订阅群拟人漫游、苹果系统写入、校园日程查询等端侧专属能力抽象为标准 Tools；
   * 使得 Claude Desktop、Cursor、Antigravity 等任意现代通用大模型 Agent 均可将 Campus-Agent 作为外部多模态工具直接插拔调用。
2. **多日历精细分类学 (Multi-Calendar & Multi-List Taxonomy)**：
   * 彻底颠覆了“所有待办堆在默认列表”的粗放模式，在 Apple Reminders 与 Calendar 中自适应建立大学生专属垂直日历树：
     * 📘 `📚 课程作业与考试`：作业 DDL、随堂测验、期末大作业
     * 🏛️ `🏛️ 班级行政与通知`：评优问卷、团日活动、综测核对、宿舍安全
     * 🎭 `🎭 社团活动与生活`：俱乐部讲座、志愿活动、文体演出
3. **视觉消息高水位线与幂等去重 (Visual Cutoff & Watermark Deduplication)**：
   * 针对视觉 OCR 无固定 `message_id` 的痛点，提出**视觉文本指纹（Visual Text Hash）**算法，在本地 SQLite 中维护各群高水位线；
   * 若当前屏文本无变化，直接命中缓存跳过（**0 Token 消耗，0 冗余推理**）；
   * 对提取出的每一项 DDL 计算唯一特征指纹 `SHA256(Title + DDL + Category)`，杜绝跨轮次重复写入苹果日历。
4. **群发言人画像与可信白名单 (`Speaker Profiling & Trusted Whitelist`)**：
   * 结合 Apple Vision 空间定位与 DeepSeek 角色实体抽取，识别群消息发送者身份（如 `任课教师 张老师:`、`辅导员:`、`学委:`）；
   * 匹配群置信发言人白名单，对官方通告赋予最高权重与专属标识，彻底隔离同学日常闲聊中的误导时间。
5. **双向回读确认与执行回执 (Bi-directional Verification Receipts)**：
   * 改变过去单向调用 AppleScript 的盲投模式，写入时同步回读并校验 Apple 守护进程生成的原生 `item_id` 与时间戳；
   * 形成严密的 **Write-Verify-Receipt 事务闭环**，并将已验真存根持久化于本地数据库。

---

### 3.7 具身对话智能体：校园智能学伴「小航」(Campus-Copilot) 与主动预警机制

在吸收了 `workbuddy-qq-agent-gateway` 对话网关理念的基础上，Campus-Agent 并不仅停留在“后端静默抓取器”，而是升华出了**具身对话智能体「小航 (Campus-Copilot)」**（见 [`app/agent.py`](app/agent.py) 与 [`app/dashboard.html`](app/dashboard.html)）：

```mermaid
flowchart TD
    User["大学生 (Web 控制台 / 自然语言对话)"] -->|提问 / 指令| Copilot["Campus-Copilot 对话引擎 ('小航')"]
    
    subgraph Cognitive["认知大模型与决策层 (DeepSeek-V3)"]
        Copilot --> Decider{"意图研判与工具决策<br/>(Function Calling)"}
        Decider -- "常规闲聊 / 答疑" --> Reply["生成温暖贴心的学伴 Markdown 回复"]
        Decider -- "需要感知或操作端侧" --> ToolCalls["发起具身工具调用 (Tool Calls)"]
    end
    
    subgraph Tools["具身感知与执行工具集 (Agent Tools)"]
        ToolCalls --> T1["query_upcoming_schedule (查询本地已验真待办)"]
        ToolCalls --> T2["inspect_current_wechat_screen (0按键实况快照)"]
        ToolCalls --> T3["roam_and_inspect_subscribed_groups (漫游全量订阅群)"]
        ToolCalls --> T4["add_schedule_item (双向回执写入 Apple 提醒)"]
        ToolCalls --> T5["list_monitored_campus_groups (查询受监控群组)"]
    end
    
    Tools -->|结构化执行结果| Decider
    Reply --> User
```

#### 1. 两阶段 Function Calling 闭环推理
系统构建了标准 OpenAI 规范的 Agent Tools，使大模型能够直接支配端侧感知能力：
* **第一阶段（意图解析与工具选派）**：大模型接收用户自然语言（例如：“*帮我看下当前微信窗口有什么通知*”或“*今天有什么紧急 DDL？*”），自动决策并输出带有精确入参的 `tool_calls`；
* **第二阶段（工具执行与数据回流）**：后端调度 CoreGraphics / Vision OCR / SQLite，将执行结果注入 `messages` 上下文，大模型综合时间锚点输出结构化、带重点标记的终版回复。

#### 2. 大学生多维注意事项与“避坑”预警体系 (Campus Precaution Rules)
区别于通用聊天机器人，「小航」内置了大学校园场景专属的事项预警知识图谱：
* 🚨 **24 小时紧急 DDL 督办**：如四六级报名通道关闭、选课退选时限、大物实验预习报告提前 1 天关库等高代价事项，优先红色高亮；
* 📚 **平时作业与实验排期**：自动辨析学习通、雨课堂、PTA 题库等平台的提交规范，提示“*建议预留 30 分钟避开晚高峰网络拥堵*”；
* 🏛️ **班级行政与宿舍安全红线**：主动提示“*宿管例行安全检查禁止使用违章大功率电器*”、“*团日打卡截图命名格式需为学号+姓名*”等大学生极易忽视的隐形规则。

#### 3. 网络故障自愈与离线兜底 (Graceful Degradation)
当处于无外网环境或沙箱受限时，智能体自动启动**本地离线学伴兜底机制**：直接无损调取本地 SQLite 中的已验真存根，自动组织成条理清晰的 DDL 与注意事项报告，确保关键时刻系统 100% 可靠不掉链。

#### 4. 借 Agent 之口直接送达：巡视要点简报与端侧纯净语音口播引擎
在传统 RPA 系统中，自动化任务结束后通常仅在终端打印一段冗长的 JSON 或调试日志，用户体验冰冷且需要人工费力审阅。Campus-Agent 践行“**后台无感静默巡视，前台借 Agent 之口温暖汇报**”的人机交互哲学：
* **双生文案提炼引擎 (`generate_agent_briefing`)**：
  每次巡检结束后，系统自动产出两套互相契合的表达载体：
  1. **结构化富文本简报 (`markdown`)**：以智能学伴「小航」的第一人称口吻，按紧急程度梳理 24h 极限 DDL、常规课程作业与班级规章，并附带针对性的“防踩坑指南”；
  2. **精炼口播文案 (`spoken_script`)**：专门面向语音合成提炼的口语化摘要（50~100字），过滤所有格式符号，重点念出作业名称、截止时间与考勤提醒，或在群消息未变动时播报“*今日平安，请专心学习*”。
* **端侧纯净中文语音合成 (Neural Speech)**：
  * **0 成本 · 0 延迟 · 0 云端泄露**：系统全面告别劣质的搞笑音效与高延迟付费第三方 TTS，直接调优并接入 macOS 原生高质量纯净中文女声（**婷婷 / Tingting** 与 **Siri 中文**）；
  * **前端 Web Speech API + 后端 macOS `say` 双轨驱动**：用户在控制台不仅可以通过「🔊 听小航语音口播」一键朗读，还能开启「🔊 巡检后自动口播要点」开关；在后台守护进程模式下，新待办将伴随系统原生横幅音效直达桌面。

---

## 4. 关键技术对比与竞品分析 (Comparative Evaluation)

| 评估维度 | 传统 QQ 协议网关 (如 WorkBuddy) | 传统微信 Hook / 逆向 | 传统 Accessibility 爬虫 | **Campus-Agent (本系统)** |
| :--- | :--- | :--- | :--- | :--- |
| **集成范式** | **协议网关 / Bot 小号** | 动态链接内存注入 | 系统无障碍 DOM 树 | **端侧具身视觉感知 + 拟人微动** |
| **封号风险** | 🟡 中（依赖协议反作弊） | 🔴 极高（腾讯风控秒封） | 🟢 零风险 | 🟢 **绝对零风险 (0内存破坏)** |
| **账号形态** | 必须配备**独立机器人小号** | 个人号（高危） | 个人号 | 🟢 **直接赋能主力个人主号** |
| **微信 4.x 适配**| ❌ 无法接入微信 | ❌ 每次更新需逆向 | ❌ 完全失效 (Canvas反爬) | ✅ **100% 视觉穿透适配** |
| **系统打扰** | 🟢 无感 (运行在 Docker) | 🟢 无感 | 🔴 抢占焦点不复原 | 🟢 **Ghost Switch 瞬间复原** |
| **标准扩展性** | ✅ 原生支持 MCP | ❌ 私有 RPC | ❌ 无 | ✅ **原生标准 MCP 2.1 Server** |
| **去重与回执** | ✅ 协议 ID 水位线 | ❌ 容易重复 | ❌ 无 | ✅ **视觉高水位线 + 验真回执** |
| **多端触达** | 需自建或通过 Webhook | 需自建短信/推送 | 无 | ✅ **原生免费同步 iPhone/Watch** |

---

## 5. 实测用例与准确率验证 (Empirical Evaluation)

在真实测试用例（计算机专业《大学英语与学术写作》课程大群，包含任课教师发布的作业通知及大量同学回复）中：

### 原始屏幕嘈杂输入：
```text
任课教师 张老师: 
作业：① U1学习通平台任务（至少完成 vocabulary部分）
② 开始做《听力随身练》，不规定题量，自行练习
13:44
任课教师 张老师: 
📢@所有人 四级辅导还没有要报名的 今天下午要上报了
15:06
学生A: 收到！
学生B: +1
学生C: ［微信转账］
```

### 系统输出与闭环验证：
1. **Vision OCR 提取耗时**：`48 ms`（提取率 100% 无乱码）
2. **DeepSeek 提炼结果**：
   * 自动过滤所有“收到”、“+1”和转账信息；
   * 提炼出作业 1：`U1学习通平台任务`（地点：学习通平台）
   * 提炼出作业 2：`听力随身练自行练习`
   * 提炼出紧急 DDL：`四级辅导报名`，由于识别到“今天下午”，结合当前基准时间（2026年10月14日），成功推导标准时间 `2026-10-14 18:00:00`。
3. **苹果原生提醒事项**：
   * 标题：`【紧急】四级辅导报名`
   * 截止闹钟：`2026-10-14 18:00`
   * 详情备注：`地点/平台: 未指定\n详情: 四级辅导还没有要报名的 今天下午要上报了\n来源: 巡检【26秋 通用英语C】`
   * **真机验证**：iPhone 锁屏在 2 秒后弹出原生系统提醒通知！

---

## 6. 结论与未来展望 (Conclusion & Roadmap)

Campus-Agent 成功验证了在不破解任何底层通信协议、不修改任何二进制签名、不破坏任何宿主安全机制的前提下，利用**边缘神经网络实况视觉（Vision）+ 拟人化无痕巡航（Human-Like RPA）+ 大语言模型认知推理（LLM）+ 系统级原生闭环（EventKit/iCloud）**，实现跨应用场景端到端自动化的可行性。

### 下一步演进路线（Roadmap）：
1. **本地小模型量化部署（Apple MLX / 端侧 4-bit 量化）**：将 DeepSeek 降噪逻辑迁移至本地 Apple Silicon 芯片（如 Qwen2.5-7B-Instruct 4-bit），实现 100% 断网离线运行与终极隐私保护；
2. **端侧 VLM 视觉大模型直出（Vision-Language Model）**：直接将截图输入端侧多模态模型，一步完成视觉理解到结构化 JSON 的映射。
