# Tasks

## 1. 依赖与配置

- [x] 1.1 `backend/requirements.txt`：新增 `langchain-chroma`、`chromadb`、`pypdf`、`docx2txt`（md/txt 直接解码，不引入 `unstructured`）；执行 `pip install -r requirements.txt` 并验证 `python -c "from langchain_chroma import Chroma; import chromadb, pypdf, docx2txt"` 导入成功
- [x] 1.2 `backend/app/core/config.py` 新增知识库配置项（11 项，默认值对齐 design.md D10）：`dashscope_api_key` / `embedding_base_url` / `embedding_model` / `embedding_dimensions` / `embedding_batch_size` / `kb_enabled` / `kb_persist_dir` / `kb_chunk_size` / `kb_chunk_overlap` / `kb_max_file_mb` / `kb_top_k` / `kb_top_k_limit`；同步更新 `backend/.env.example`；验证 `Settings()` 可加载且无 key 时默认降级
- [x] 1.3 `backend/app/core/exceptions.py` 新增 `DocumentParseError`(5003) / `KbDocumentNotFoundError`(4004)，纳入统一异常处理器；验证错误码与 message 契约
- [x] 1.4 `backend/app/llm/langchain_factory.py` 新增 `get_embeddings()`（百炼 `text-embedding-v4`，`check_embedding_ctx_length=False` + `chunk_size=10` + `dimensions=1024`）；新建 `backend/tests/test_embeddings_factory.py` 断言参数锁定（无网络依赖）

## 2. 文档解析与向量存储

- [x] 2.1 新建 `backend/app/llm/doc_loaders.py`：`parse_document_to_text`（md/txt 解码 `utf-8-sig → gbk → utf-16`；pdf 用 `PyPDFLoader`；docx 用 `Docx2txtLoader`；bytes 落临时文件先 close 再加载，用后即删；空文本抛 `DocumentParseError`、不支持格式/空内容抛 `InvalidInputError`）与 `split_text_to_chunks`（`RecursiveCharacterTextSplitter`，中文优先分隔符，`chunk_size=500`/`overlap=50`）；新建 `backend/tests/test_doc_loaders.py` 覆盖多编码、pdf/docx、异常、分块粒度与重叠
- [x] 2.2 新建 `backend/app/services/kb_store.py`：`KbStore`（单一 `chromadb.PersistentClient`，collection `user_{id}`）—— `add_chunks`（元数据 `doc_id`/`filename`，ids `doc{id}_{i}_{uuid8}`）、`search`（`where={"doc_id":{"$in":...}}`，异常返空降级）、`sample`（纯 metadata 取概览，不触发 embedding）、`delete_document`（底层 `collection.delete(where=...)` 幂等）、`get_kb_store()` 单例；新建 `backend/tests/test_kb_store.py`（真实 Chroma 本地持久化 + 确定性 fake embedding）覆盖增/查/删、`doc_id` 过滤、用户隔离、collection 不存在容错

## 3. 知识库服务与数据模型

- [x] 3.1 `backend/app/db/orm_models.py` 新增 `KbDocument` 表（`kb_documents`）：`id`/`user_id`(FK)/`filename`/`doc_type`/`file_size`/`char_count`/`chunk_count`/`status`(default processing)/`error`/`created_at`/`updated_at`，索引 `idx_kb_docs_user_time`；验证 `init_db` 幂等建表
- [x] 3.2 新建 `backend/app/models/kb.py`（DTO）：`KbDocStatus=Literal["processing","ready","failed"]`、`KbDocumentItem`、`KbDocumentPage`、`KbUploadResult`
- [x] 3.3 新建 `backend/app/services/kb_service.py`：`create_document`（校验 `kb_enabled`/`dashscope_api_key`/扩展名/非空/大小 → 建行 `processing` → 落盘 `uploads/kb/{user_id}/{doc_id}.{ext}`）、`process_document`（后台任务自建 session：解析 → 分块 → `add_chunks` → `ready`；异常兜底 `failed`+`error` 截断 255，绝不抛；仅 processing 时幂等处理）、`list_documents`/`get_document`/`delete_document`（向量+原始文件+记录三者幂等清理）、`get_ready_doc_ids`（归属+ready 校验，否则 4001）；新建 `backend/tests/test_kb_service.py` 覆盖上传校验、状态机、就绪校验、删除幂等

## 4. 接口层

- [x] 4.1 新建 `backend/app/api/v1/routes/kb.py`：`POST /kb/documents`（`BackgroundTasks` 调度 `process_document`，返回 `doc_id`+`processing`）、`GET /kb/documents`（`limit`/`offset` 分页）、`GET /kb/documents/{doc_id}`、`DELETE /kb/documents/{doc_id}`；四接口全 `Depends(get_current_user)`（仅本人）；在 v1 路由聚合注册
- [x] 4.2 `backend/app/api/deps.py` 新增 `get_kb_service(db)`（`KbService(db, get_kb_store())`）与 `get_optional_user`（无 Token 返 None，无效 Token 仍 4010）
- [x] 4.3 新建 `backend/tests/test_kb_api.py`：四接口未登录 4010、上传受理返回 processing、列表分页、详情仅本人、删除；`pytest tests/test_kb_api.py -q` 全绿

## 5. Agentic RAG 集成

- [x] 5.1 `backend/app/llm/research_tools.py` 新增 `build_kb_search_tool(settings, *, user_id, doc_ids, kb_store)`：构建期锁定 `user_id`/`doc_ids`，agent 只控 `query`/`k`（`Field(default=kb_top_k, ge=1, le=kb_top_k_limit)`）；`asyncio.to_thread` 下放同步检索；返回带来源文件名片段（双层 `_clip` 截断），无结果引导文本，异常返回 `_KB_UNAVAILABLE`；`backend/tests/test_research_tools.py` 补 `kb_search` 用例（锁定、截断、降级）
- [x] 5.2 `backend/app/services/research_service.py`：`_build_research_agent(*, user_id, kb_doc_ids)` 按可用性组装工具集（tavily key → 联网双工具，user_id+kb_doc_ids → `kb_search`）；`system_prompt_for(with_kb)` 追加 `_KB_ADDENDUM`（私有优先）；`research(user_input, *, user_id, kb_doc_ids)` 判 `kb_usable` + 静默降级；`_cache_key` 加 `|u{id}|kb{docs}` 维度；`ResearchOutcome` 新增 `topic`；自动出题 `_kb_overview`/`_AUTO_MODE_HEAD`+`_TAIL`/`_auto_fallback_or_degraded`；`backend/tests/test_research_service.py` 补工具集组装、缓存维度、自动出题概览与兜底、降级用例
- [x] 5.3 `backend/app/services/quiz_service.py`：`_run_research` 传 `user_id`/`kb_doc_ids`；`_with_auto_topic`（空输入用 `outcome.topic` 替换，回退 `AUTO_KB_TOPIC`）；`generate_quiz_sync`/`run_generation` 支持 kb；`backend/app/prompts/quiz_prompt.py` 新增 `AUTO_KB_TOPIC`；`backend/tests/test_quiz_service.py` 补自动出题主题回填、kb 参数透传用例
- [x] 5.4 `backend/app/api/v1/routes/quiz.py`：`GenerateQuizRequest` 新增 `kb_doc_ids`（`max_length=10`，`model_validator` 保证空输入必选文档）；`_preprocess` 空输入跳过长度校验；`_validate_kb_selection`（空返 None 链路不变；非空要求登录 4010 + `get_ready_doc_ids` 4001）；`generate`/`generate_sync` 用 `get_optional_user`；`backend/tests/test_api.py` 补 `kb_doc_ids` 校验与匿名兼容用例
- [x] 5.5 全量回归 `pytest tests/ -q`（沙箱需 `--basetemp=.tmp` 指向工作区内）：**230 passed**，既有出题 / 研究 / 报告 / 用户链路零破坏

## 6. 前端

- [x] 6.1 `frontend/src/types/index.ts` 新增 `KbDocument`/`KbDocumentPage`/`KbUploadResult`；`frontend/src/services/api.ts` 新增 `getKbDocuments`/`uploadKbDocument`（`Taro.uploadFile` 带 Token）/`deleteKbDocument`；`submitQuizTask` 增加可选 `kb_doc_ids`
- [x] 6.2 新建 `frontend/src/pages/kb`（`index.tsx`/`index.scss`/`index.config.ts`）：`Taro.chooseMessageFile`（extension `pdf/docx/md/txt`）上传、列表（状态徽标 解析中/可出题/解析失败 + 失败原因）、删除（二次确认）、选择模式（`?mode=select` 勾选 `ready`，最多 10 个，回填 store）；有 `processing` 文档时 3s 轮询刷新至全终态；`frontend/src/app.config.ts` 注册 `pages/kb/index`
- [x] 6.3 `frontend/src/store/quiz.ts` 的 `QuizState` 增加 `kbDocIds`/`kbDocNames` 与 `setKbSelection(docIds, docNames)`；首页知识库选择区入口与空输入放行（选了文档可留空主题）；`generating` 页提交携带 `kb_doc_ids` 与阶段文案；验证 `npx tsc --noEmit` src 零错误 + `npm run build:weapp` 构建成功

## 7. 端到端验收

> 验收中发现并解决的环境问题（非代码缺陷）：本机 `DASHSCOPE_API_KEY` 注册表已删但 Qoder IDE 进程环境块仍缓存旧版失效 key（`sk-`+32hex），pydantic-settings 优先 `os.environ` 导致真实向量化 401；旧 uvicorn 进程占用 8000 端口致新脚本后端未起。经「进程内清除环境变量 + 干净启动 + MySQL 在线」完整验证真实 RAG 端到端通过。

- [x] 7.1 后端干净环境真实端到端（httpx 全链路，MySQL 在线）：登录 → 上传 md（`doc_id`+processing）→ 后台真实百炼向量化 `ready`（chunks/chars 有值）→ 带 `kb_doc_ids` 出题 `research_used=True` → 3 题全部精准基于私有文档（如住宿费阈值、工作日时限、金额边界）→ 删除文档 200
- [x] 7.2 知识库自动出题验收：选中知识库文档 + 留空主题，核对研究智能体预取概览自推主题、`kb_search` 深入检索、题目围绕文档内容展开
- [x] 7.3 降级与兼容验收：a) 未配 `DASHSCOPE_API_KEY` 时上传报友好错误、出题忽略文档选择退回纯联网/纯模型且任务不失败；b) 匿名不带 `kb_doc_ids` 出题链路与改造前逐字一致；c) 携带无效 `kb_doc_ids`（非本人/未就绪）返回 4001
- [x] 7.4 微信开发者工具端到端：首页进入知识库页上传文档、轮询至「可出题」、勾选文档出题、generating 页阶段文案、答题与报告不受影响；`pytest` 全量回归 230 passed（用户确认开发测试完成）
