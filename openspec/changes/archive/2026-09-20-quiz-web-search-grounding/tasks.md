   # Tasks

## 1. 配置与依赖

- [x] 1.1 `backend/requirements.txt`：升级 `langchain>=1.0`，新增 `langgraph>=1.0`、`langchain-tavily`（实测最新版为 0.2.18，版本约束修正为 `>=0.2.0`）；执行 `pip install -r requirements.txt` 并验证 `python -c "from langchain.agents import create_agent; from langchain_tavily import TavilySearch, TavilyExtract"` 导入成功
- [x] 1.2 依赖升级后先跑全量回归：`pytest tests/ -q` 确认现有链路（ChatPromptTemplate / ChatOpenAI / with_structured_output）在 langchain 1.x 下无破坏（98 passed；沙箱环境需 `--basetemp=.tmp` 指向工作区内）
- [x] 1.3 `backend/app/core/config.py` 新增研究配置项（11 项，默认值对齐 design.md D9），`deepseek_model` 默认值改为 `deepseek-flash`；同步更新 `backend/.env.example`；验证 `Settings()` 可加载且默认值正确
- [x] 1.4 本地 `backend/.env` 已同步：`DEEPSEEK_MODEL=deepseek-flash`、`TAVILY_API_KEY=`（空，待用户在 https://tavily.com 注册后填入）；无 key 时后端启动与 health 检查验证通过（降级路径）

## 2. 研究工具与智能体

- [x] 2.1 新建 `backend/app/llm/research_tools.py`：用 `@tool` 定义 `web_search`（参数：`query`、`search_depth`、`max_results`（ge=1, le=research_results_limit）、`time_range`、`country`、`include_domains`/`exclude_domains`、`include_full_content`；docstring 写明参数选择策略：复杂/新兴主题用 advanced + 全文、简单主题用摘要、中文主题建议 country="china"）与 `web_extract`（参数：`urls`（1~3 条）、`extract_depth`）；内部经 langchain-tavily 自带的 `TavilySearchAPIWrapper`/`TavilyExtractAPIWrapper` 直连（实测 0.2.x 不依赖 tavily-python，实现时修正，design.md D2 已同步），`include_full_content=True` 时传 `include_raw_content + include_answer + advanced`；实现单源与整体双层截断；工具异常返回降级文本而非抛异常；新建 `backend/tests/test_research_tools.py` 覆盖参数透传、边界拒绝、截断、异常降级（14 passed）
- [x] 2.2 `backend/app/llm/output_schemas.py` 新增 `ResearchSource` / `ResearchSummary`（`topic_domain` / `context_digest` / `sources`）；`backend/app/llm/langchain_factory.py` 新增 `get_research_model()`（temperature 取 `research_temperature`）；验证模块可独立导入（schema 实例化与 deepseek-flash/0.2 工厂验证通过）
- [x] 2.3 新建 `backend/app/services/research_service.py`：`ResearchProvider` 协议预留扩展点；`ResearchService` 组装研究智能体（`create_agent` + 双工具 + `response_format=ResearchSummary` + `RESEARCH_SYSTEM_PROMPT`（URL 优先抓取、新术语先确认领域、资料不足换参数重搜、次数有限够用即收尾）+ `ToolCallLimitMiddleware` / `ModelCallLimitMiddleware`）；`research(user_input)` 编排：总开关检查、`asyncio.wait_for` 总超时、`ResearchSummary` 拼接为 `ResearchOutcome.context_text`（截断到 `research_context_max_chars`）、SHA-256 key 的进程内 TTL 缓存（降级结果不缓存）、未配置 key 直接降级；新建 `backend/tests/test_research_service.py` 覆盖：正常产出、超时/异常降级、无资料降级、未配置 key 降级、缓存命中（第二次不执行研究）、拼接截断（13 passed；`research_timeout` 配置项实现时放宽为 float 以支持亚秒级测试与更精细控制，默认 60 不变）

## 3. Prompt v2

- [x] 3.1 `backend/app/prompts/quiz_prompt.py` 升级 `QUIZ_PROMPT_VERSION = "quiz_prompt_v2"`：`quiz_meta_prompt` 与 `quiz_question_prompt` 新增 `{research_context}` 变量（user 消息新增「参考资料」区块，无资料时传 `NO_RESEARCH_CONTEXT` 占位常量），`QUIZ_QUESTION_SYSTEM` 增加资料优先/领域消歧/禁止编造/改写讲解四条指令（追加为第 8~11 条，现有 1~7 原样保留；meta system 补一句资料镄定引导）；更新 `backend/tests/test_prompt_contract.py` 断言新版本号、变量集合含 `research_context`、format 无异常（7 passed）

## 4. 出题链路与任务状态

- [x] 4.1 `backend/app/llm/quiz_chain.py`：`QuizGenerator` 协议的 `generate_meta` / `generate_question` 增加 `research_context: str` 参数（不设默认值），`LangChainQuizGenerator` 两个 chain 的 `ainvoke` 传入该变量；同步更新 `quiz_service.py` 调用点（临时传 `NO_RESEARCH_CONTEXT` 占位，4.3 替换为研究产出）与 `tests/conftest.py` 的 `FakeQuizGenerator` mock 签名（顺带记录 research_context 供 4.3 断言）；`test_quiz_service` / `test_api` / `test_prompt_contract` 共 26 项全绿
- [x] 4.2 `backend/app/models/quiz.py` 的 `TaskState` 新增 `phase: str = ""` 与 `research_used: bool | None = None`（字段带默认值，`model_dump()` 向后兼容已验证）；`backend/app/services/task_store.py` 新增 `set_phase` / `set_research_used` 方法（与既有 setter 同风格，未知任务不抛错已验证）
- [x] 4.3 `backend/app/services/quiz_service.py` 编排改造：`QuizService` 构造器注入 `ResearchService`（默认 `get_research_service()` 单例）；`run_generation` 与 `generate_quiz_sync` 在生成 meta 前调用 `research`，将 `context_text` 传给生成器，研究降级时记录日志并继续出题；`run_generation` 更新 `phase`（researching → generating）与 `research_used`；更新 `backend/tests/test_quiz_service.py`：断言 research 先于 meta 调用（研究产出传入 meta 与全部单题）、`research_context` 正确传入生成器、降级时任务仍完成、TaskState phase/research_used 变迁正确（新增 4 个编排用例，既有用例全部改为注入受控 `FakeResearchService`，不依赖环境 .env 状态）
- [x] 4.4 更新 `backend/tests/test_api.py`：client fixture 注入 `FakeResearchService`（不依赖环境 `TAVILY_API_KEY` 状态）；轮询接口响应断言含 `phase`（done 后为 "generating"）与 `research_used`（mock 降级为 false）字段且不破坏既有断言；`pytest tests/ -q` 全量通过（131 passed）

## 5. 前端适配

- [x] 5.1 `frontend/src/types/index.ts` 的 `TaskState` 增加可选字段 `phase?: string`、`research_used?: boolean | null`；`frontend/src/pages/generating/index.tsx` 在 `phase === 'researching'` 时气泡文案切换为「小智正在全网检索最新资料…拿到最新知识就开始出题」（store 解构新增 phase，`isResearching = phase === 'researching' && status !== 'done'`）；`frontend/src/pages/index/index.tsx` 输入框 placeholder 追加「粘贴网页链接也可以」；`store/quiz.ts` 的 `QuizState` 增加 `phase: string`（初始/reset 为空串，`ingestTask` 透传 `state.phase ?? ''`）；验证 `npx tsc --noEmit` src 零错误 + `npm run build:weapp` 构建成功（node_modules 内 Taro 组件库类型噪音为既有状况，与本次改动无关）

## 6. 端到端验收

> 验收中发现的实施修正（已修复并全量回归 133 passed）：
> 1. **思考模式互斥**：deepseek-flash 默认开启思考模式，与两条结构化链路的强制 tool_choice 互斥（400 "Thinking mode does not support this tool_choice"）；新增 `DEEPSEEK_THINKING=disabled` 配置并经 `extra_body` 显式禁用（真实探针验证：禁用后 tool_choice 强制恢复）。
> 2. **Wrapper 必传参数**：`raw_results_async` 的 `include_images`/`topic` 等 9+6 个参数无默认值必传，包装工具漏传报 TypeError（宽松 **kwargs mock 未暴露）；已补齐全部必传参数（未暴露给模型的项传 None），并新增动态签名契约测试（test_research_tools.py 2 项）防回归。
>
> 修复后真实验证：出题链路 2.9s 恢复；研究链路 30.6s 真实检索 "Harness Engineering" 成功（8 条来源、完整领域消歧）。待用户重启后端继续下列验收。

- [x] 6.1 新术语真实链路验收：启动后端（配置真实 `TAVILY_API_KEY`），用 `POST /api/v1/quiz/generate/sync` 输入 "Harness Engineering"，核对题目领域锚定检索资料（AI 编码智能体领域的 harness 工程，而非线束/安全带等其他领域）、讲解基于最新资料；观察日志中研究智能体的工具调用与参数选择是否符合自适应策略（复杂主题 → advanced/全文，简单主题 → basic 摘要，条数与地区参数合理）（用户确认验收通过）
- [x] 6.2 网页链接输入验收：用 `POST /api/v1/quiz/generate/sync` 输入一篇真实网页 URL（可混合一句中文描述），核对 AI 自主调用抓取工具、题目与讲解围绕该页面内容展开（用户确认验收通过）
- [x] 6.3 国内外主题对比验收：分别用中文主题（如「微信小程序 分包加载」）与英文主题（如 "Tauri 2.0 mobile"）出题，核对地区参数（country）选择与资料源语言匹配（用户确认验收通过）
- [x] 6.4 护栏与降级演练：a) 观察正常任务的工具/模型调用次数不超过 middleware 上限；b) 临时清空 `TAVILY_API_KEY` 重启后端再出一次题，验证任务正常完成、日志记录降级原因、`research_used` 为 false；c) 相同输入重复提交，验证缓存命中（日志无第二次工具调用）（用户确认验收通过；b 项另经自动化冒烟验证）
- [x] 6.5 微信开发者工具端到端：首页输入新术语主题提交，generating 页出现「小智正在全网检索最新资料…」阶段文案，首题就绪后正常答题、报告生成不受影响；粘贴链接输入走通全流程；`pytest` 全量回归通过（用户确认验收通过；pytest 全量 133 passed）
