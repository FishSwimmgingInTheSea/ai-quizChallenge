# Proposal

## Why

大模型存在训练数据知识截止：当用户想学很新或很冷门的知识时（例：输入 "Harness Engineering"，DeepSeek 把它混淆为其他领域的同名概念），现有出题链路（`LangChainQuizGenerator` 只把 `user_input` 直接喂给模型）会生成领域错位、事实过时的题目与讲解，且无从校准。需求分析文档核心功能第 1~2 条（输入可以是一句话/一个网页，AI 自动从全网获取知识）因此一直未落地。

前期调研已确认关键事实：DeepSeek API **没有**原生联网搜索能力（官方文档兼容性明细明确 Responses API 的 `web_search` 等内置工具会被忽略），因此必须集成第三方搜索 API 在出题前做检索增强（grounding）。

用户人工思路（本轮决策）进一步要求：用户输入可能是**关键词**也可能是**网页链接**，联网能力必须同时覆盖「按关键词搜索」与「按网址抓取整页内容」；两类工具都要提供给 AI，**由 AI 自主决定何时调用哪个工具**，并**动态选择工具参数**（复杂知识搜索结果直接含完整内容、简单知识只要摘要、动态调整结果条数、动态调整地区范围以兼顾国内外用户）。

## What Changes

- **新增 AI 自主联网研究阶段**：出题任务提交后，先进入研究阶段——基于 LangChain 官方 `create_agent` 将两个工具（关键词搜索 `web_search`、网页抓取 `web_extract`，基于 `langchain-tavily` 的 `TavilySearch`/`TavilyExtract` 能力封装）绑定给研究智能体，由模型自主决定调用哪个工具、何时调用、传什么参数；研究产出结构化总结（主题领域判定、资料要点、来源列表），拼接为参考资料上下文注入题库元信息与单题生成 Prompt（升级为 `quiz_prompt_v2`），并明确指示模型：题目与讲解必须以参考资料为准、主题所属领域以资料为准、资料不足时才可基于内部知识补充。
- **支持网页链接输入**：用户输入包含 URL 时，AI 自主调用网页抓取工具获取整页内容作为核心资料（对齐需求文档「输入可以是一个网页」）。
- **研究参数动态自适应**：模型按主题复杂度与地区动态选择参数——复杂/新兴知识用深度搜索并在结果中包含完整页面内容，简单知识用基础摘要搜索；动态调整结果条数；按输入语言与主题地区动态调整地区范围参数（Tavily 为国家级参数），兼顾国内外用户。
- **全自动触发**：所有出题请求默认先研究再出题，用户无感知，不加前端开关（用户已确认）。
- **失败静默降级**：研究超时/工具连续失败/无结果/配额耗尽/未配置密钥时不阻塞主流程，降级为现有纯模型出题路径，并在日志与任务状态中记录降级原因。
- **任务进度可观测**：`TaskState` 新增研究阶段反馈（前端 generating 页展示「正在全网检索资料…」等阶段文案，最小 UI 改动，轮询协议向后兼容）。
- **研究产出缓存与成本护栏**：相同输入（清洗后哈希）的研究产出做进程内 TTL 缓存；单任务工具调用次数与模型调用次数由 middleware 硬性限制（对齐方案 §14.4 成本控制）。
- **默认模型名升级**：DeepSeek 官方已于 2026-07-24 停用旧模型名 `deepseek-chat`，默认模型升级为现行轻量主力模型 `deepseek-flash`（API 调用方式不变，仅改 `config.py` 默认值与 `.env.example`，用户已确认）。
- **新增依赖与配置**：`requirements.txt` 升级 `langchain>=1.0`，新增 `langgraph`、`langchain-tavily`；新增 `TAVILY_API_KEY` 及研究参数配置项。

## Capabilities

### New Capabilities

- `quiz-generation`: AI 自主联网研究的出题能力——研究智能体自主调用搜索/抓取双工具并动态选择参数（含地区自适应）、支持网页链接输入、以资料锚定出题（领域消歧与时效校准）、研究失败降级容错、任务研究阶段进度可观测、研究产出缓存与成本护栏。

### Modified Capabilities

（项目当前没有任何既有规格，`openspec/specs/` 为空，故无被修改的能力。）

## Impact

- **后端代码**：
  - 新增研究智能体模块：自定义 `web_search` / `web_extract` 工具（封装 Tavily 搜索与抓取）、研究智能体编排（`create_agent` + 结构化研究总结 + 调用次数护栏 + TTL 缓存 + 降级）
  - `app/services/quiz_service.py`：出题编排插入研究步骤，研究上下文传递至生成器
  - `app/llm/quiz_chain.py`：`QuizGenerator` 协议与 `LangChainQuizGenerator` 接受参考资料上下文
  - `app/prompts/quiz_prompt.py`：Prompt 升级 v2（参考资料区块 + 资料优先指令）
  - `app/models/quiz.py`：`TaskState` 新增研究阶段字段（向后兼容）
  - `app/core/config.py` / `.env.example`：Tavily 与研究配置项、默认模型名改 `deepseek-flash`
- **前端代码**：`pages/generating` 进度文案适配新阶段（可选：首页输入提示提及支持粘贴链接）；`types` 中 `TaskState` 类型同步
- **依赖**：`requirements.txt` 升级 `langchain>=1.0`，新增 `langgraph`、`langchain-tavily`（`tavily-python` 随其引入）
- **外部服务**：Tavily API（搜索 + 抓取，需申请 key，免费 1000 credits/月）、DeepSeek API 模型名变更
- **测试**：研究服务与工具封装单测、quiz_service 降级与编排集成测试、Prompt 契约测试更新
