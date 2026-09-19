# Design

## Context

见 proposal.md「Why」。当前出题链路：`POST /quiz/generate` → 后台任务 `QuizService.run_generation` → `LangChainQuizGenerator.generate_meta / generate_question`（`ChatPromptTemplate | with_structured_output`，function calling 模式）逐题生成，Prompt 仅含 `user_input`，无任何外部资料来源。任务状态由进程内 `TaskStore` 维护，前端 generating 页轮询展示「已出 N/总数」。

已确认的关键约束（调研 + 用户两轮决策）：

1. DeepSeek API 无原生联网搜索（官方兼容性明细：Responses API 的 `web_search` 等内置工具被忽略），必须集成第三方搜索 API。
2. 搜索服务商选定 **Tavily**，通过 LangChain 官方集成包 `langchain-tavily` 接入；**双工具**：`TavilySearch`（关键词搜索）+ `TavilyExtract`（按 URL 抓取整页内容）。
3. **工具绑定给 AI 自主决策**（用户人工思路）：由模型自主决定何时调用哪个工具、传什么参数；参数动态自适应——复杂知识搜索结果直接含完整内容、简单知识只要摘要、动态调整结果条数、动态调整地区范围（兼顾国内外用户）。
4. 研究编排采用 **`create_agent` 官方路径**（用户已确认）：接受新增 `langgraph` 依赖与 `langchain` 升级 1.x。
5. 研究失败**静默降级**、全自动触发（不加前端开关）。
6. 默认模型名从已停用的 `deepseek-chat` 升级为 `deepseek-flash`（官方 2026-07-24 停用旧名，`deepseek-flash` 为现行轻量主力模型，OpenAI 兼容调用方式不变）。
7. 原方案设计文档 §5.4「不引入 Agent/工具调用」的边界由用户本轮人工思路**明确推翻**：本设计引入受控的研究智能体（仅研究阶段），出题阶段仍保持单题循环 + 结构化输出的既有架构。

官方文档关键事实（已核实，决定实现方式）：

- `TavilySearch` 调用时模型可动态设置：`query`、`search_depth`、`time_range`、`include_domains`/`exclude_domains`、`include_images`；`include_answer` 与 `include_raw_content`（全文）**调用时锁定**，仅实例化可配。
- `max_results` 与 `country`（Tavily 原生 API 的国家级地区参数，仅 topic=general 生效）不在官方工具调用时动态参数清单中。
- `TavilyExtract` 调用时可动态设置 `urls`（必需）、`extract_depth`。
- `create_agent(model, tools)` 是官方 agent 标准路径（`from langchain.agents import create_agent`，需 `langgraph`）；支持 `response_format` 结构化输出；`langchain.agents.middleware` 提供 `ToolCallLimitMiddleware` / `ModelCallLimitMiddleware` 调用次数护栏。

## Goals / Non-Goals

**Goals:**

- 研究阶段：双工具（搜索 + 抓取）绑定给模型，自主决定调用与参数；参数动态自适应（深度/全文/条数/地区）。
- 支持网页链接输入：AI 自主抓取 URL 页面全文作为核心资料。
- 研究产出结构化总结并注入出题 Prompt，解决知识截止导致的领域错位（如 "Harness Engineering" 被混淆为其他领域）。
- 研究不可用（超时/失败/无 key/无结果）时降级为现有出题路径，任务不失败。
- 硬性成本护栏：工具/模型调用次数上限、研究总超时、研究产出 TTL 缓存。
- 出题对外数据结构完全不变（前端零适配即可渲染）。

**Non-Goals:**

- 报告链路（`report_chain`）联网研究——报告基于题库与答题记录，无需外部资料。
- 多源输入解析（PDF/Word/视频）、RAG 私有知识库、向量数据库（需求文档 P1 另立项；本变更仅覆盖网页 URL）。
- 前端展示研究来源引用 UI（资料来源仅进入日志与 Prompt，不进题目展示）。
- 出题阶段动态调用工具（研究仅发生在出题前的独立阶段；单题生成循环不绑定工具，保持既有架构）。
- 搜索服务商抽象的多实现落地（仅以 Protocol 预留扩展点，不实现博查/Firecrawl 等备选）。
- SSE / 城市级地区参数（Tavily 地区参数为国家级 `country`，无城市粒度）。

## Decisions

### D1: 研究阶段采用 `create_agent` + 双工具，出题阶段架构不变

新增 `app/services/research_service.py`。编排顺序（`run_generation` / `generate_quiz_sync` 内）：`research（agent + 双工具） → meta → 逐题`。

```python
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware

research_agent = create_agent(
    model=research_model,          # 独立低温度模型（见 D9）
    tools=[web_search, web_extract],  # 自定义包装工具（见 D2）
    response_format=ResearchSummary,  # 结构化研究总结（见 D3）
    system_prompt=RESEARCH_SYSTEM_PROMPT,
    middleware=[
        ToolCallLimitMiddleware(run_limit=settings.research_max_tool_calls),
        ModelCallLimitMiddleware(run_limit=settings.research_max_model_calls),
    ],
)
result = await research_agent.ainvoke({"messages": [("user", user_input)]})
summary: ResearchSummary = result["structured_response"]
```

- 模型自主决策完全交给官方 agent 循环（工具调用 → ToolMessage 回填 → 再决策 → 结构化收尾），不自写 while 循环。
- 护栏用官方 middleware：工具调用与模型调用分别限次；研究整体再套 `asyncio.wait_for` 总超时。
- 备选（已否决）：手动 `bind_tools` + 自写循环——零新依赖但要自维护回填/护栏/收尾；用户已确认采用官方路径。
- 出题阶段（meta + 单题循环）**保持现有代码路径完全不变**，只是 `research_context` 的来源从「无」变为「研究总结拼接」。

### D2: 自定义包装工具 `web_search` / `web_extract`，绕开官方工具的调用时参数锁定

官方 `TavilySearch`/`TavilyExtract` 工具的调用时动态参数面**不满足**用户需求（`include_raw_content`、`max_results`、`country` 均锁定或缺失）。因此用 LangChain 标准 `@tool` 定义两个包装工具（`app/llm/research_tools.py`），内部直连 langchain-tavily 自带的 API Wrapper（`TavilySearchAPIWrapper` / `TavilyExtractAPIWrapper`，aiohttp 直连 REST API——实测 0.2.x 已不依赖 `tavily-python`，此为 apply 阶段核实的修正），参数显式暴露给模型：

```python
@tool
async def web_search(
    query: str,
    search_depth: Literal["basic", "advanced"] = "basic",
    max_results: int = Field(default=5, ge=1, le=8),
    time_range: Literal["day", "week", "month", "year"] | None = None,
    country: Literal["china", "united states", "united kingdom", ...] | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    include_full_content: bool = False,
) -> str:
    """联网搜索公开资料。……docstring 说明每个参数的含义与选择策略
    （复杂/新兴主题：search_depth="advanced" + include_full_content=True；
    简单主题：默认摘要即可；中文主题建议 country="china"，
    英文主题可不传或选对应国家；条数按需在 1~8 调整）……"""
```

```python
@tool
async def web_extract(
    urls: list[str] = Field(min_length=1, max_length=3),
    extract_depth: Literal["basic", "advanced"] = "basic",
) -> str:
    """按网址抓取整页内容。输入包含网页链接时使用本工具。……"""
```

- `include_full_content=True` 时底层调用传 `include_raw_content=True` + `search_depth="advanced"`，并附 `include_answer=True`——官方锁定的初衷是防上下文爆炸，本包装在工具内做等效保护：每条结果的全文截断到 `research_per_source_max_chars`（默认 2500 字符），返回整体截断到 `research_tool_output_max_chars`（默认 6000 字符）。
- `country` 为 Tavily 原生 API 的国家级地区参数（仅 topic=general 生效，取值为小写国家全称枚举）；暴露常用子集 + docstring 引导，实现「兼顾国内外用户」的地区自适应。Tavily 无城市级参数（用户所述"城市范围"以国家级参数落地）。
- `max_results` 用 Pydantic `ge/le` 约束在 1~8，防模型传超大值。
- 工具返回值为截断后的纯文本（含来源标题与 URL），错误时返回「工具暂时不可用」文本而非抛异常（让 agent 自行决定换路或收尾，同时服务层降级兜底）。
- 备选（已否决）：子类化 `TavilySearch` 扩展 `args_schema`——依赖官方内部实现细节，版本升级易碎。
- 备选（已否决）：直接把官方 `TavilySearch`/`TavilyExtract` 实例绑给 agent——无法满足动态全文/条数/地区的需求（调用时锁定）。

### D3: 研究产出结构化 `ResearchSummary`，服务层拼接为 `research_context`

```python
# app/llm/output_schemas.py 新增
class ResearchSource(BaseModel):
    title: str
    url: str

class ResearchSummary(BaseModel):
    topic_domain: str = Field(description="用户主题所属领域的判定与术语含义（领域消歧依据）")
    context_digest: str = Field(description="供出题引用的资料要点汇编（核心概念、关键事实、时效信息）")
    sources: list[ResearchSource] = Field(description="资料来源列表")
```

- agent 的 `response_format=ResearchSummary` 保证收尾输出结构化总结（与现有 `with_structured_output` 同构的 ToolStrategy）。
- `ResearchOutcome`（服务层对象）：`context_text`（`topic_domain` + `context_digest` + 来源列表拼接为资料块，整体截断到 `research_context_max_chars`，默认 6000 字符）、`sources`、`degraded`、`degrade_reason`。
- `RESEARCH_SYSTEM_PROMPT` 要点：判定用户输入是否包含 URL（有则优先 `web_extract` 抓全文）；新术语先搜索确认领域含义；资料不足可换 query/参数再搜；次数有限、够用即收尾；不得编造资料中不存在的内容。
- 与 `QuizGenerator` 协议同构：`QuizService` 通过构造器注入 `ResearchService`，测试注入 mock（复用现有测试模式）。

### D4: 进程内 TTL 缓存研究产出（key = 清洗后输入的 SHA-256）

`ResearchService` 内置 `dict[key, (outcome, timestamp)]` + 锁，TTL `research_cache_ttl_seconds`（默认 900s），风格与 `TaskStore` 一致（单机单进程假设，将来多实例时与 TaskStore 一并迁 Redis）。缓存对象是**研究产出整体**（agent 的 query 是模型动态生成的，无法按单次搜索缓存）；失败/降级结果**不缓存**，避免一次网络抖动导致后续请求长时间无资料。

### D5: Prompt v2 —— 参考资料区块 + 资料优先指令

`app/prompts/quiz_prompt.py` 升级 `QUIZ_PROMPT_VERSION = "quiz_prompt_v2"`：

- `quiz_meta_prompt` 与 `quiz_question_prompt` 均新增输入变量 `{research_context}`；无资料时传固定占位文本「（本次未获取到检索资料）」。
- `QUIZ_QUESTION_SYSTEM` 新增指令（要点）：
  1. 「参考资料」区块内的信息优先级高于模型内部知识；两者冲突（含主题所属领域、术语含义、事实时效）时以参考资料为准。
  2. 若用户主题是与多个领域同名的术语，必须按参考资料确认的领域含义出题，禁止使用其他领域的同名概念。
  3. 资料不足以覆盖主题时，才允许基于内部知识合理补充，不得编造资料中不存在的内容。
  4. 讲解不得逐字复述资料原文，须改写为通俗表达。
- 现有指令（题型结构、JSON 约束、避免重复等）原样保留，`test_prompt_contract.py` 同步断言新变量集合与版本号。

### D6: `QuizGenerator` 协议扩展 `research_context` 参数

`generate_meta` / `generate_question` 签名各增加 `research_context: str`（Protocol 显式声明，不设默认值，强制所有实现与 mock 同步更新）。`LangChainQuizGenerator` 的两个 chain `ainvoke` 时多传该变量。出题结果 Schema（`QuestionDraft` 等）不变。

### D7: `TaskState` 新增 `phase` 与 `research_used` 字段（不动 status 枚举）

- 备选 A（已否决）：扩展 `status` 枚举加 `researching` 值——status 表达任务生命周期（pending/generating/done/failed），混入步骤语义会污染前端轮询终止条件判断，且是对既有枚举的破坏性修改。
- 选定：`TaskState` 增加 `phase: str = ""`（`"researching"` / `"generating"`，空串表示旧语义）与 `research_used: bool | None = None`（null=研究中/未知）。两字段均有默认值，`model_dump()` 输出向后兼容，旧前端忽略新字段。
- `TaskStore` 新增 `set_phase(task_id, phase)` 与 `set_research_used(task_id, used)` 方法（与既有 setter 同风格）。
- `run_generation` 编排：`set_status("generating")` + `set_phase("researching")` → research（写缓存/降级日志）→ `set_phase("generating")` + `set_research_used(...)` → meta → 逐题（现有逻辑不动）。

### D8: 前端最小改动：generating 页阶段文案 + 首页提示

- `frontend/src/types/index.ts` 的 `TaskState` 增加可选 `phase?: string`、`research_used?: boolean | null`。
- `pages/generating/index.tsx` 气泡文案按 `phase === 'researching'` 切换为「小智正在全网检索最新资料…」，进度条与题目列表逻辑不变。
- 首页输入框 placeholder 追加「粘贴网页链接也可以」（提示用户支持 URL 输入，纯文案改动）。
- `store/quiz` 的 `ingestTask` 原样透传新字段（Pydantic `model_dump` 已包含）。

### D9: 配置项、模型与依赖升级

`app/core/config.py` / `.env.example` 新增：

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `TAVILY_API_KEY` | `""`（空） | Tavily 密钥；空 = 自动降级 |
| `RESEARCH_ENABLED` | `True` | 研究总开关（紧急关断） |
| `RESEARCH_MAX_TOOL_CALLS` | `6` | 单任务工具调用次数上限（middleware） |
| `RESEARCH_MAX_MODEL_CALLS` | `8` | 单任务模型调用次数上限（middleware） |
| `RESEARCH_TIMEOUT` | `60` | 研究阶段总超时（秒） |
| `RESEARCH_TEMPERATURE` | `0.2` | 研究模型温度（事实性优先，低温度） |
| `RESEARCH_RESULTS_LIMIT` | `8` | `max_results` 参数上限（工具 schema 的 le） |
| `RESEARCH_PER_SOURCE_MAX_CHARS` | `2500` | 单条来源全文截断 |
| `RESEARCH_TOOL_OUTPUT_MAX_CHARS` | `6000` | 单次工具输出截断 |
| `RESEARCH_CONTEXT_MAX_CHARS` | `6000` | 注入出题 Prompt 的资料字符预算 |
| `RESEARCH_CACHE_TTL_SECONDS` | `900` | 研究产出缓存 TTL（秒） |

`deepseek_model` 默认值 `"deepseek-chat"` → `"deepseek-flash"`（config.py 默认值、`.env.example`、apply 时提醒用户更新本地 `.env`）；新增 `DEEPSEEK_THINKING=disabled`（验收中实测：deepseek-flash 不传 thinking 时默认开启思考模式，思考模式与结构化输出的强制 tool_choice 互斥——研究 ToolStrategy 收尾与出题 `with_structured_output(function_calling)` 均 400 "Thinking mode does not support this tool_choice"；`extra_body={"thinking": {"type": "disabled"}}` 已验证完全恢复，故默认禁用，保留配置项供将来实验）。

`requirements.txt`：`langchain>=1.0`（升级，`create_agent` 所需）、新增 `langgraph>=1.0`、`langchain-tavily>=0.2.0`（实测 PyPI 最新为 0.2.18；自带 aiohttp API Wrapper，不引入 `tavily-python`）；`langchain-core`/`langchain-openai` 由 pip 解析为兼容版本。现有代码（`ChatPromptTemplate`、`ChatOpenAI`、`with_structured_output`）在 langchain 1.x 下向后兼容（langchain-core 稳定性承诺）。

`langchain_factory.py` 新增 `get_research_model()`（temperature 取 `research_temperature`），研究/出题/报告三个模型共用工厂模式不变。

### D10: 测试策略

- `tests/test_research_tools.py`（新增）：mock Tavily 客户端——工具参数透传（`include_full_content` → `include_raw_content + advanced`）、`max_results` 边界拒绝、全文与整体截断生效、工具异常返回降级文本、URL 抓取参数。
- `tests/test_research_service.py`（新增）：mock 研究智能体（`ResearchService` 通过注入工厂跳过真实 agent）——正常产出、超时降级、异常降级、无资料降级、未配置 key 降级、缓存命中（第二次不执行研究）、`context_text` 拼接与截断。
- `tests/test_quiz_service.py`（更新）：注入 mock research + mock generator——断言编排顺序（research 先于 meta）、`research_context` 传入生成器、降级时仍完成出题、TaskState phase/research_used 变迁。
- `tests/test_prompt_contract.py`（更新）：v2 版本号、meta/question prompt 的 `input_variables` 含 `research_context`、format 无异常。
- `tests/test_api.py`（更新）：轮询响应含 `phase` 字段且默认值兼容。
- 手动验收：后端起服务后用 `Harness Engineering`（新术语）、粘贴一篇网页 URL、中文主题三类输入走 `/quiz/generate/sync`，人工核对题目领域锚定、URL 内容覆盖、地区适配与讲解质量。

## Risks / Trade-offs

- [langchain 1.x + langgraph 升级的兼容性风险（现有 ChatPromptTemplate/ChatOpenAI/测试基线）] → langchain-core 向后兼容承诺；apply 阶段先跑全量 pytest 回归再继续；`langchain-openai` 同步升级。
- [模型自主调用工具的成本与耗时波动（多轮决策）] → middleware 双限次（工具 6 / 模型 8）+ 总超时 60s + TTL 缓存；DeepSeek context caching 自动命中（system prompt 与工具定义稳定），降低多轮成本。
- [研究阶段拉长首题就绪时间（一轮工具调用 1~3s × 多轮）] → 异步任务 + 「正在检索」阶段反馈，用户无白屏等待；超时硬上限后必降级；护栏默认值偏保守可调。
- [包装工具绕开官方调用时锁定的 `include_raw_content`，上下文膨胀] → 包装层双层截断（单源 2500 / 单工具输出 6000 字符）实现官方限制的等效初衷。
- [模型选择参数不当（如简单主题滥用全文）] → 工具 docstring 明确选择策略引导；护栏兜底最坏情况；观测日志记录每次工具调用与参数，便于调优。
- [Tavily 对中文主题检索质量一般] → `country` 地区参数 + 模型可换 query 重试；`ResearchProvider` 协议预留博查等国产搜索替换空间；资料不足时降级路径保证可用。
- [免费配额 1000 credits/月耗尽（搜索与抓取共享 credits）] → TTL 缓存 + `research_enabled` 开关 + 配额/鉴权错误自动降级，链路不中断。
- [`deepseek-flash` 在 Chat Completions 下的默认思考行为未验证] → **已验证并修复**：默认开启思考模式，与强制 tool_choice 互斥（两个结构化链路均 400）；经 `extra_body` 显式禁用后真实调用恢复（出题 2.9s / 研究 30.6s，8 条来源）。保留 `DEEPSEEK_THINKING` 配置项。
- [Tavily API Wrapper 的必传位置参数] → **验收中实测**：`raw_results_async` 的 `include_images`/`topic` 等参数无默认值必传，漏传报 TypeError；包装工具已补齐全部必传参数（未暴露给模型的项传 None），并新增动态签名契约测试（test_research_tools.py）防回归。
- [境外搜索服务在国内服务器的可达性波动] → 60s 总超时 + 降级兜底；生产部署如持续不可达，按协议替换 provider。

## Migration Plan

1. 安装依赖：`pip install -r requirements.txt`（升级 langchain 1.x、新增 langgraph / langchain-tavily）。
2. 升级后先跑全量 `pytest` 回归，确认既有链路在 langchain 1.x 下无破坏，再实施新功能。
3. 配置：`.env` 增加 `TAVILY_API_KEY`（https://tavily.com 免费注册），`DEEPSEEK_MODEL` 改为 `deepseek-flash`；无 `TAVILY_API_KEY` 时功能自动降级，可先行部署代码。
4. 无数据库迁移（题目结构、库表不变）；前端仅需重新编译发布。
5. 回滚：`.env` 置 `RESEARCH_ENABLED=false` 即关闭研究回到纯模型出题（代码回滚亦可，对外契约无破坏性变更）。

## Open Questions

- `deepseek-flash` 思考模式的显式控制参数（若联调发现默认开启思考导致 agent 多轮变慢/思维链占用输出 token）——按 DeepSeek 官方「思考模式」文档处理，属配置级调整。
- 工具 docstring 的参数选择策略措辞调优（观察日志中模型的实际参数选择后迭代）——不影响结构，属 Prompt 微调。
- 研究资料对出题质量的量化验收标准（如「新术语题目领域正确率」）——先以手动验收 + 日志观察为准，后续再定量化基线。
