# Proposal

## Why

现有出题链路的资料只有一个来源——公网（`quiz-web-search-grounding` 已让 AI 自主联网搜索/抓取）。但大量学习场景的资料是**私有、非公开**的：企业内部制度、内部培训材料、指定教材/讲义、自有题库等，这些内容公网搜不到，大模型训练数据里也没有。用户无法基于自己的私有文档出题学习，需求分析文档「输入可以是一句话 / 一个网页 / 一份资料」中的「私有资料」一直缺位。

同时，前序 `quiz-web-search-grounding` 已搭好「出题前研究智能体（`create_agent` + 工具集）」的骨架，为把「私有知识库检索」作为研究智能体的**第三个工具**接入提供了天然扩展点——无需新架构，只增加向量库与一个工具，即可让 AI 在出题时**自主决定**：查私有知识库、联网搜索，还是两者结合。

## What Changes

- **新增用户私有知识库（RAG）**：用户可上传 pdf / docx / md / txt 文档建立个人知识库；后端解析 → 分块 → 百炼 `text-embedding-v4` 向量化 → 写入 Chroma（每用户独立 collection + `doc_id` 元数据隔离）；提供列表 / 详情 / 删除管理；文档处理为后台异步任务，状态机 `processing → ready / failed`。
- **出题接入 Agentic RAG**：出题请求新增可选 `kb_doc_ids`；选中知识库文档时，研究智能体额外获得 `kb_search` 工具（与 `web_search` / `web_extract` 并列），由 AI 自主决定私有检索与联网搜索的取舍；私有资料优先、公网补充。
- **知识库自动出题**：选中知识库文档但**留空学习主题**时，系统预取文档概览，由 AI 自推主题并检索出题（用户无需先想主题）。
- **可选登录（向后兼容）**：出题接口保持匿名可用——仅当携带 `kb_doc_ids` 时才要求登录并校验文档归属与就绪状态；不选知识库时链路与改造前完全一致。
- **静默降级**：知识库不可用（未配置向量模型密钥 / 开关关闭 / 匿名请求 / 检索异常）时，静默忽略文档选择，退回纯联网或纯模型出题，任务不失败。
- **新增依赖与配置**：新增 `langchain-chroma`、`chromadb`、`pypdf`、`docx2txt`，以及百炼 embedding 与知识库参数配置项。

## Capabilities

### New Capabilities

- `knowledge-base`: 用户私有知识库能力——文档上传受理与格式/大小校验、后台解析分块与向量化入库、每用户向量隔离、文档列表/详情/删除管理、面向出题的语义检索、处理状态机与失败降级。

### Modified Capabilities

- `quiz-generation`: 出题研究阶段从「仅联网」扩展为「私有知识库 + 联网，AI 自主取舍」——新增 `kb_search` 工具与私有资料优先、选中知识库文档出题（可选登录 + 就绪校验）、知识库自动出题（空输入自推主题）、知识库不可用静默降级；不选知识库时行为与既有逐字一致。

## Impact

- **后端代码**：
  - 新增 `app/llm/doc_loaders.py`（pdf/docx/md/txt 解析 + 中文优先分块）
  - 新增 `app/services/kb_store.py`（Chroma 封装：每用户 collection + `doc_id` 隔离 + search/sample/delete）
  - 新增 `app/services/kb_service.py`（上传受理 / 后台解析向量化 / CRUD / 出题就绪校验）
  - 新增 `app/api/v1/routes/kb.py`（文档上传/列表/详情/删除，均需登录）、`app/models/kb.py`（DTO）
  - `app/db/orm_models.py`：新增 `KbDocument` 表（`kb_documents`）
  - `app/llm/langchain_factory.py`：新增 `get_embeddings()`（百炼 `text-embedding-v4`）
  - `app/llm/research_tools.py`：新增 `build_kb_search_tool()`（Agentic RAG 第三工具）
  - `app/services/research_service.py`：`research` 接受 `user_id`/`kb_doc_ids`，组装 `kb_search`、私有优先提示词、自动出题概览、缓存 key 加用户/文档维度、降级兜底
  - `app/services/quiz_service.py`：出题编排传递 kb 参数、自动出题主题回填
  - `app/api/v1/routes/quiz.py`：`kb_doc_ids` 校验（可选登录 + 就绪）、空输入跳过长度校验
  - `app/api/deps.py`：`get_kb_service` / `get_optional_user`
  - `app/core/config.py` / `.env.example`：百炼 embedding 与知识库配置项
  - `app/core/exceptions.py`：`DocumentParseError`(5003) / `KbDocumentNotFoundError`(4004)
- **前端代码**：新增 `pages/kb`（知识库管理：上传/列表/删除/选择）；`store/quiz.ts` 增加 `kbDocIds`/`kbDocNames`/`setKbSelection` 与自动出题主题；首页知识库选择区与空输入放行；`generating` 页携带 `kb_doc_ids` 与阶段文案；`services/api.ts` 增加 kb 接口；`app.config.ts` 注册页面
- **依赖**：`requirements.txt` 新增 `langchain-chroma`、`chromadb`、`pypdf`、`docx2txt`（md/txt 直接解码，不引入 unstructured）
- **外部服务**：阿里云百炼（DashScope）OpenAI 兼容 embedding（`text-embedding-v4`，需 `DASHSCOPE_API_KEY`）
- **数据库**：新增 `kb_documents` 表（`init_db` 幂等建表，无破坏性迁移）
- **测试**：doc_loaders 解析分块、kb_store 隔离与检索、kb_service 状态机与校验、kb 路由鉴权、research_service 的 kb 集成与自动出题、quiz 路由 `kb_doc_ids` 校验；全量回归 230 passed
- **零影响保证**：`kb_doc_ids` 为空 / 未选知识库时，出题链路与改造前逐字一致（研究智能体工具集、缓存 key、prompt 均不含 kb 分支）
