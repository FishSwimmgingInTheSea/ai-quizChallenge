# Design

## Context

见 proposal.md「Why」。前序 `quiz-web-search-grounding` 已把出题链路改造为「出题前研究智能体（`create_agent` + 工具集 + 结构化收尾）→ meta → 逐题」，研究阶段目前仅有两个联网工具（`web_search` / `web_extract`）。本变更在**同一骨架**上把「用户私有知识库检索」接入为研究智能体的**第三个工具** `kb_search`，不改动出题阶段（meta + 单题循环）架构。

当前出题链路：`POST /quiz/generate` → 后台任务 `QuizService.run_generation` → `ResearchService.research`（agent + 工具）→ `LangChainQuizGenerator.generate_meta / generate_question`。任务状态由进程内 `TaskStore` 维护，前端 generating 页轮询展示阶段与进度。

已确认的关键约束（调研 + 用户决策）：

1. 私有资料（企业制度、内部培训、指定教材/题库）公网搜不到，必须以用户自己的文档为出题依据。
2. 向量库选型 **Chroma**（本地持久化，零外部服务），每用户一个 collection，文档以 `doc_id` 元数据区分。
3. 向量模型选型**阿里云百炼（DashScope）`text-embedding-v4`**，经 OpenAI 兼容接口调用（复用现有 `langchain-openai`）。
4. **文档处理走后台异步任务**（上传受理与解析向量化分离），状态机 `processing → ready / failed`，避免大文件解析阻塞请求。
5. **Agentic RAG**：`kb_search` 与 `web_search` / `web_extract` 并列，由 AI 自主决定私有检索与联网搜索的取舍；私有资料优先、公网补充。
6. **向后兼容零影响**：出题接口保持匿名可用，仅当携带 `kb_doc_ids` 时才要求登录；不选知识库时链路与改造前逐字一致。
7. **静默降级**：知识库任何不可用路径（未配 key / 开关关闭 / 匿名 / 检索异常）都不让出题任务失败。

百炼 embedding 关键事实（已核实，决定实现方式）：

- OpenAI 兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`；新版密钥格式为 `sk-ws` 开头、含 `.`/`_`、约 116 字符（旧版 `sk-` + 32 hex 已不可用于 embedding）。
- `text-embedding-v4` 单请求最多 **10 行**文本；`OpenAIEmbeddings` 必须 `chunk_size=10` 分批，且 `check_embedding_ctx_length=False`（DashScope 非原生 OpenAI 端点，关闭本地 tiktoken 长度自查，否则嵌入请求报错），`dimensions=1024`。

## Goals / Non-Goals

**Goals:**

- 用户上传 pdf / docx / md / txt 建私有知识库：解析 → 中文优先分块 → 百炼向量化 → 写入 Chroma（每用户 collection + `doc_id` 隔离）。
- 知识库文档管理：列表 / 详情 / 删除（均需登录，仅本人可操作）；处理状态机 `processing → ready / failed`。
- 出题接入 Agentic RAG：选中文档时研究智能体额外获得 `kb_search`，AI 自主决定私有检索与联网取舍。
- 知识库自动出题：选中知识库文档但留空主题时，预取概览由 AI 自推主题检索出题。
- 出题可选登录：仅携带 `kb_doc_ids` 时要求登录并校验归属与就绪；不选知识库时链路逐字不变。
- 知识库不可用时静默降级，任务不失败。

**Non-Goals:**

- 扫描件 / 图片型 PDF 的 OCR（无文字层的文档解析为空即报 `DocumentParseError`）。
- 多用户共享知识库、知识库分组 / 标签、全文关键词检索（仅向量语义检索）。
- 服务端 Chroma / 分布式向量库（MVP 单进程本地持久化，多实例部署时再迁移）。
- 报告链路（`report_chain`）接入知识库——报告基于题库与答题记录，无需外部资料。
- 前端展示知识库来源引用 UI（来源文件名仅进入 Prompt 与日志）。
- 出题阶段（单题循环）动态调用工具——检索仅发生在出题前的研究阶段。

## Decisions

### D1: 向量库 Chroma —— 每用户一 collection + `doc_id` 元数据隔离

新增 `app/services/kb_store.py`。`KbStore` 封装 langchain-chroma：

- **单一 `chromadb.PersistentClient`** 贯穿实例生命周期（同一 persist 目录必须复用 client，否则 sqlite 锁冲突）；生产经 `get_kb_store()` 全局单例。
- collection 命名 `user_{id}`（满足 Chroma 命名约束 `^[a-zA-Z0-9._-]{3,63}$`），实现**用户级物理隔离**。
- 文档级隔离靠 `add_chunks` 写入的 `doc_id` / `filename` 元数据；`search` 用 `where={"doc_id": {"$in": doc_ids}}` 过滤到选中文档集合。
- 向量 id 用 `doc{doc_id}_{i}_{uuid8}`（可重复入库不撞 id）；`delete_document` 走底层 `collection.delete(where={"doc_id": ...})`（langchain 包装的 delete 仅支持按 id），幂等（collection 不存在静默）。
- `sample` 纯 metadata 读取（`collection.get`，不触发 embedding 网络调用），供自动出题取概览。
- 一切检索 / 取样 / 删除异常均捕获后返回空或静默，由上层降级。
- 备选（已否决）：单一 collection + `user_id` 元数据过滤——隔离弱、误召回风险高；每用户 collection 物理隔离更稳妥。

### D2: 百炼 `text-embedding-v4` —— OpenAI 兼容接口，参数锁定

`app/llm/langchain_factory.py` 新增 `get_embeddings()`（`@lru_cache` 单例）：

```python
OpenAIEmbeddings(
    model=settings.embedding_model,          # text-embedding-v4
    api_key=settings.dashscope_api_key,
    base_url=settings.embedding_base_url,    # .../compatible-mode/v1
    dimensions=settings.embedding_dimensions,# 1024
    chunk_size=settings.embedding_batch_size,# 10（百炼单请求最多 10 行）
    check_embedding_ctx_length=False,        # 非原生 OpenAI 端点必须关闭
)
```

- 未配置 `dashscope_api_key` 时不在工厂抛错，由调用方（`KbService.create_document` 上传受理、`ResearchService` 出题）先行检查后降级，保证无 key 也能启动。
- embedding 模型与出题 / 研究 / 报告三个 chat 模型共用工厂风格，仅参数不同。

### D3: 文档解析 + 中文优先分块

新增 `app/llm/doc_loaders.py`，`ALLOWED_KB_EXTS = {pdf, docx, md, txt}`：

- **md / txt**：直接解码，兜底顺序 `utf-8-sig → gbk → utf-16`（Windows 记事本常见 GBK）；不引入 `unstructured` 重依赖（`.md` 无需结构感知分块，决策已人工确认）。
- **pdf**：`langchain-community` 的 `PyPDFLoader`（`pypdf` 提取文字层）；**docx**：`Docx2txtLoader`（`docx2txt`）。Loader 需文件路径，bytes 先落临时文件（Windows 下 `NamedTemporaryFile` 必须 `delete=False` + 先 close 再交 Loader），用后即删。
- 提取不到有效文本（扫描件 / 图片型）抛 `DocumentParseError`(5003)；格式不支持 / 内容为空抛 `InvalidInputError`(4001)。
- **分块** `split_text_to_chunks`：`RecursiveCharacterTextSplitter`，分隔符兼顾中文段落与句读 `["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]`，`chunk_size=500` / `chunk_overlap=50`（可配）。

### D4: 上传受理与后台向量化分离的状态机

新增 `app/services/kb_service.py`（`KbService` 注入 `db` + `KbStore`）：

- **`create_document`（请求内同步）**：校验 `kb_enabled` / `dashscope_api_key` / 扩展名 / 非空 / 大小（`kb_max_file_mb`）→ 建 MySQL 行（`status="processing"`）→ 原始文件落盘 `uploads/kb/{user_id}/{doc_id}.{ext}` → 返回 `doc_id` + `processing`。
- **`process_document`（后台任务）**：路由用 `BackgroundTasks.add_task` 调度，响应返回后执行；**内部自建 session**（`sessionmaker(bind=self._db.get_bind())`，请求级 Session 届时已关闭）；FastAPI 对同步后台任务自动走线程池。流程：读盘 → 解析 → 分块 → `add_chunks` → 写 `char_count` / `chunk_count` / `status="ready"`。
- **异常兜底不抛**：后台任务无人接异常，`process_document` 捕获一切异常置 `status="failed"` + `error`（截断 255）+ `commit`，绝不向上抛。
- **幂等保护**：仅当行存在、属于本人、且仍为 `processing` 时才处理（避免重复后台任务）。
- `get_ready_doc_ids`：出题前校验选中 `doc_ids` 须全部属于本人且 `ready`，否则 `InvalidInputError`(4001)。
- 备选（已否决）：上传时同步解析向量化——大文件 + 远程 embedding 会阻塞请求数十秒，体验差且易超时。

### D5: `kb_search` 作为研究智能体第三工具

`app/llm/research_tools.py` 新增 `build_kb_search_tool(settings, *, user_id, doc_ids, kb_store)`：

- **构建期锁定** `user_id` + `doc_ids`（服务层判定可用后注入），agent 只能控制 `query` 与 `k`（`Field(default=kb_top_k, ge=1, le=kb_top_k_limit)`），杜绝越权检索他人 / 未选文档。
- `KbStore.search` 为同步且内部含远程 embedding 网络调用，经 `asyncio.to_thread` 下放工作线程，避免阻塞事件循环。
- 返回带来源文件名的原文片段（单源截断 `research_per_source_max_chars` / 整体截断 `research_tool_output_max_chars`，与联网工具同一 `_clip` 预算）；无结果返回引导文本（换词或改用 `web_search`）；异常返回 `_KB_UNAVAILABLE` 降级文本而非抛异常。
- docstring 写明选择策略：私有领域资料联网搜不到，应优先 `kb_search`；query 贴近原文措辞召回更准；不足时增大 k 或换词。

### D6: 研究服务按数据源可用性组装工具集 + 私有优先提示词

`app/services/research_service.py` 扩展（不改 `create_agent` 官方路径）：

- `_build_research_agent(*, user_id, kb_doc_ids)` **按可用性组装工具集**：`tavily_api_key` 已配 → `build_research_tools`（联网双工具）；`user_id + kb_doc_ids` 可用 → 追加 `kb_search`。两者独立，任一缺失只少对应工具。
- `system_prompt_for(with_kb)`：选了知识库时在 `RESEARCH_SYSTEM_PROMPT` 后追加 `_KB_ADDENDUM`（私有资料优先、`context_digest` 标注哪些要点摘自私有库）；未选时提示词逐字不变。
- `research(user_input, *, user_id, kb_doc_ids)`：先判 `kb_usable`（`kb_requested and kb_enabled and dashscope_api_key`），不可用则**静默忽略选择**（`effective_*` 置 None）退回纯联网，记 warning。
- **缓存 key 加维度**：`_cache_key` 在归一化输入后追加 `|u{user_id}|kb{sorted docs}`（知识库内容因人而异，跨用户不可共享）；不选知识库时 scope 为空串，key 与改造前一致。
- `ResearchOutcome` 新增 `topic`（研究智能体判定的学习主题，供自动出题空输入时兜底出题 prompt）。

### D7: 知识库自动出题（空输入自推主题）

空输入 + 知识库可用 = 自动出题模式：

- `_kb_overview`：`store.sample(user_id, doc_ids, per_doc=2)` 取每文档开头若干 chunks（纯元数据读取，代价低），拼为概览（`_clip` 到工具输出预算）。
- 概览注入用户消息（`_AUTO_MODE_HEAD` + overview + `_AUTO_MODE_TAIL`），指令 agent 先推断核心主题（`topic_domain` 写明）再用 `kb_search` 深入检索；概览为空则降级（无从推断）。
- `QuizService._with_auto_topic`：空 `user_input` 时用 `outcome.topic` 替换进入出题 prompt，研究未产出主题则回退固定文案 `AUTO_KB_TOPIC`（「知识库文档自动出题」），出题链路不因空主题断掉。
- `_auto_fallback_or_degraded`：自动出题模式下 agent 超时 / 异常 / 无产出时，**概览原文直接作出题资料**（`degraded=True`），承诺不落空。

### D8: 出题可选登录 + 就绪校验（向后兼容）

- `GenerateQuizRequest` 新增 `kb_doc_ids: list[int] | None`（`max_length=10`）；`model_validator` 保证「空输入必须选知识库文档」。
- `app/api/deps.py` 新增 `get_optional_user`：无 Token 返 `None`（匿名放行），无效 Token 仍 `UnauthorizedError`(4010)。
- `routes/quiz.py` 的 `_validate_kb_selection`：`kb_doc_ids` 为空 → 返回 `None`，链路逐字不变；非空 → 要求登录（否则 4010）+ `get_ready_doc_ids` 校验（否则 4001）→ 返回 `user_id` 传出题编排。
- `_preprocess`：空输入（自动出题）跳过长度校验，长度下限仅约束用户手写主题。

### D9: 前端知识库管理页与选择流

- 新增 `pages/kb`（`app.config.ts` 注册，从首页进入，不占 tabBar）：`Taro.chooseMessageFile`（extension `pdf/docx/md/txt`）上传、列表（状态徽标 解析中 / 可出题 / 解析失败）、删除、选择模式（`?mode=select` 勾选 `ready` 文档，最多 10 个，回填 store）；有 `processing` 文档时 3s 轮询刷新至全终态。
- `store/quiz.ts` 的 `QuizState` 增加 `kbDocIds` / `kbDocNames` 与 `setKbSelection(docIds, docNames)`；首页知识库选择区与空输入放行；`generating` 页携带 `kb_doc_ids` 与阶段文案；`services/api.ts` 新增 `getKbDocuments` / `uploadKbDocument` / `deleteKbDocument`；`types/index.ts` 新增 `KbDocument` / `KbDocumentPage` / `KbUploadResult`。

### D10: 配置项与依赖

`app/core/config.py` / `.env.example` 新增：

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `DASHSCOPE_API_KEY` | `""`（空） | 百炼密钥；空 = 知识库不可用（上传报错 / 检索降级） |
| `EMBEDDING_BASE_URL` | `.../compatible-mode/v1` | 百炼 OpenAI 兼容端点 |
| `EMBEDDING_MODEL` | `text-embedding-v4` | 向量模型 |
| `EMBEDDING_DIMENSIONS` | `1024` | 向量维度 |
| `EMBEDDING_BATCH_SIZE` | `10` | 单请求最大文本条数（百炼限 10 行） |
| `KB_ENABLED` | `True` | 知识库总开关（紧急关断） |
| `KB_PERSIST_DIR` | `kb_data` | Chroma 持久化目录（相对运行目录） |
| `KB_CHUNK_SIZE` / `KB_CHUNK_OVERLAP` | `500` / `50` | 分块大小 / 重叠（字符） |
| `KB_MAX_FILE_MB` | `10` | 单文档大小上限 |
| `KB_TOP_K` / `KB_TOP_K_LIMIT` | `4` / `8` | `kb_search` 默认 / 最大检索条数 |

`app/core/exceptions.py` 新增 `DocumentParseError`(5003) / `KbDocumentNotFoundError`(4004)。`requirements.txt` 新增 `langchain-chroma`、`chromadb`、`pypdf`、`docx2txt`（md/txt 直接解码，不引入 `unstructured`）。

### D11: 测试策略（后端 TDD）

- `test_doc_loaders.py`：md/txt 多编码解码、pdf/docx 解析、空文本 / 不支持格式抛业务异常、中文分块粒度与重叠。
- `test_embeddings_factory.py`：`get_embeddings()` 参数锁定（model / dimensions / chunk_size / check_embedding_ctx_length）。
- `test_kb_store.py`：真实 Chroma 本地持久化 + 确定性 fake embedding——增 / 查 / 删、`doc_id` 过滤、用户隔离、collection 不存在容错。
- `test_kb_service.py`：上传校验（开关 / key / 扩展名 / 空 / 超限）、后台处理状态机（ready / failed 兜底不抛）、`get_ready_doc_ids` 归属与就绪校验、删除幂等。
- `test_kb_api.py`：四接口鉴权（未登录 4010）、上传受理返回 processing、列表分页、删除。
- `test_research_service.py` / `test_research_tools.py` / `test_quiz_service.py`（更新）：`kb_search` 构建期锁定与降级、工具集按可用性组装、私有优先提示词、缓存 key 加维度、自动出题概览与兜底、空输入主题回填。
- 全量回归 230 passed；真实百炼端到端（登录 → 上传 → 向量化 ready → 带 kb 出题 `research_used=True` → 题目精准基于私有文档 → 删除）验证通过。

## Risks / Trade-offs

- [百炼 embedding 远程调用配额 / 网络波动] → `process_document` 异常兜底 `failed`（不抛）；`kb_search` 异常返回降级文本；研究层整体降级；缓存复用降低重复调用。
- [大文件解析 + 向量化耗时长] → 后台异步任务 + 状态机，上传即时返回 `processing`，前端轮询进度；`kb_max_file_mb` 限制单文件大小。
- [Chroma 单进程本地持久化，多实例部署 sqlite 锁冲突] → 单一 PersistentClient 复用；MVP 单进程假设，多实例时按 persist_dir 分片或换服务端 Chroma（`KbStore` 已封装隔离改动面）。
- [每用户一 collection，用户量大时 collection 数膨胀] → MVP 规模可接受；Chroma collection 轻量，超大规模再评估共享 collection + 元数据隔离。
- [向量维度 / 模型变更导致旧向量失效] → `kb_persist_dir` 可整体重建（原始文件已落盘 `uploads/kb`，可重跑 `process_document`）。
- [百炼新版 key 格式（`sk-ws` 116 字符）与旧版混淆导致 401] → 文档与 `.env.example` 注明；实测确认新版 key 有效（旧 `sk-` + 32 hex 不可用于 embedding）。
- [私有资料泄露到公网检索 / 跨用户召回] → collection 物理隔离 + `kb_search` 构建期锁定 `user_id`/`doc_ids` + `search` 的 `where` 双重过滤；缓存 key 加用户 / 文档维度不跨用户共享。

## Migration Plan

1. 安装依赖：`pip install -r requirements.txt`（新增 `langchain-chroma` / `chromadb` / `pypdf` / `docx2txt`）。
2. 配置：`.env` 增加 `DASHSCOPE_API_KEY`（阿里云百炼控制台申请，新版 `sk-ws` 格式）；无 key 时知识库功能自动降级（上传报错、出题忽略文档选择），可先行部署代码。
3. 数据库：`init_db` 幂等建 `kb_documents` 表，无破坏性迁移；Chroma 首次写入时自建 `kb_data` 目录。
4. 前端：重新编译发布（新增 `pages/kb`，`app.config.ts` 已注册）。
5. 回滚：`.env` 置 `KB_ENABLED=false` 即关闭知识库（上传报错、出题退回纯联网 / 纯模型），对外契约无破坏性变更；代码回滚亦安全。

## Open Questions

- 知识库检索质量的量化验收标准（如「私有文档题目命中率」）——先以真实端到端 + 日志观察为准，后续再定量化基线。
- `kb_search` docstring 的参数选择策略措辞调优（观察日志中模型的实际调用后迭代）——不影响结构，属 Prompt 微调。
- 是否需要知识库文档的「重新解析」入口（当前失败文档只能删除重传）——按用户反馈再定，属增量功能。
