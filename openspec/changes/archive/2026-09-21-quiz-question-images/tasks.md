# Tasks

## 1. 依赖与配置

- [x] 1.1 `backend/requirements.txt` 新增 `dashscope`、`cos-python-sdk-v5`；`pip install -r requirements.txt` 后验证 `python -c "import dashscope, qcloud_cos, httpx"` 导入成功
- [x] 1.2 `backend/app/core/config.py` 新增配置项：`image_gen_enabled: bool = False`、`dashscope_image_model = "qwen-image-2.0"`、`image_size = "512*512"`、`image_daily_limit: int = 20`、`image_gen_timeout: int = 30`、`image_prompt_max_len: int = 300`、`image_negative_prompt`、`cos_secret_id`、`cos_secret_key`、`cos_bucket`、`cos_region`；同步更新 `backend/.env.example`（COS/密钥仅占位，不写真值）；验证 `Settings()` 可加载且无凭据时 `image_gen_enabled` 默认 False
- [x] 1.3 `backend/app/core/exceptions.py`（如需）确认无新增错误码需求——配图全程静默降级，不新增业务异常码；记录该决策

## 2. 数据模型与迁移

- [x] 2.1 `backend/app/models/quiz.py`：`Question` 加 `image_url: str = ""`、`GenerateQuizRequest` 加 `generate_images: bool = False`、`TaskState` 加 `image_notice: str = ""`；`backend/app/models/user.py`：`RecordQuestionItem` 加 `image_url: str = ""`；验证 `pytest tests/test_models.py -q` 全绿、默认值向后兼容
- [x] 2.2 `backend/app/db/orm_models.py`：新增 `ImageGenUsage` 表（`image_gen_usage`：`id`/`user_id`(FK)/`usage_date`(Date)/`count`，`UNIQUE(user_id, usage_date)`）；`QuizQuestionRecord` 加 `image_url VARCHAR(500) NOT NULL DEFAULT ''`；验证内存 SQLite `init_db` 幂等建表成功
- [x] 2.3 在 design.md 的迁移说明基础上，产出 MySQL 手动迁移语句（`ALTER TABLE quiz_record_items ADD COLUMN image_url VARCHAR(500) NOT NULL DEFAULT '';`）写入变更目录 `migration.sql`，供用户上线时执行；`image_gen_usage` 由 `create_all` 自动建，无需手动

## 3. 生图与存储封装（TDD）

- [x] 3.1 先写 `backend/tests/test_image_prompt.py`：`build_image_prompt(question)` 依题干/知识点/正确选项产出相关提示词、含固定风格后缀、超长截断到 `image_prompt_max_len`；再实现 `backend/app/llm/image_gen.py` 的 `build_image_prompt` 纯函数使测试通过
- [x] 3.2 先写 `backend/tests/test_image_gen.py`：Mock `dashscope.MultiModalConversation.call` 与 `httpx` 下载，验证 `DashScopeImageGenerator.generate(prompt) -> bytes`（解析临时 URL、下载字节、超时/异常返回 None 或抛出被上层捕获）；定义 `ImageGenerator` Protocol；再实现 `image_gen.py` 生图封装（`asyncio.to_thread` 下放同步调用）使测试通过
- [x] 3.3 先写 `backend/tests/test_cos_store.py`：Mock `qcloud_cos.CosS3Client`，验证 `CosImageStore.upload(bytes, key) -> 永久URL`（`put_object` + `get_object_url`，对象键含 user/年月/uuid，凭据缺失返回不可用）；定义 `ImageStore` Protocol；再实现 `backend/app/services/cos_store.py` 使测试通过

## 4. 配额与配图服务（TDD）

- [x] 4.1 先写 `backend/tests/test_usage_service.py`（内存 SQLite）：当日计数递增、达上限判定、跨自然日重置、并发/重复调用不超发（原子自增）；再实现 `backend/app/services/usage_service.py`（仿 `kb_service` 自建 session，`has_quota(user_id)` + `increment(user_id)`，`INSERT ... ON CONFLICT DO UPDATE`）使测试通过
- [x] 4.2 先写 `backend/tests/test_image_service.py`：用 Fake `ImageGenerator`/`ImageStore`/`UsageService` 覆盖 D6 全部降级分支——总开关关、未登录、缺密钥/凭据、额度用尽、生图/上传异常，均返回 None 且产出对应 `image_notice`；成功路径返回永久 URL 且计数递增；再实现 `backend/app/services/image_service.py`（`generate_for_question(question, *, user_id) -> tuple[str|None, str|None]`、惰性导入 SDK、全程 try/except 降级、日志留痕）使测试通过

## 5. 出题编排接入（TDD）

- [x] 5.1 `backend/app/services/task_store.py` 新增 `set_question_image(task_id, index, url)`、`set_image_notice(task_id, notice)`（幂等：已设不覆盖），`set_phase` 支持 `imaging`；在 `backend/tests/test_task_store.py` 补用例并验证通过
- [x] 5.2 先扩展 `backend/tests/test_quiz_service.py`：`run_generation`/`generate_quiz_sync` 注入 Fake `image_service`，验证 `generate_images=True`+登录时逐题并发触发、题目回填 `image_url`、进入 `imaging` 阶段；单题生图失败仅该题不带图、任务仍 `done`；`generate_images=False` 或未登录时不触发生图、链路与既有一致；再改 `backend/app/services/quiz_service.py`（注入 `image_service`、D1 并发 + `asyncio.gather(return_exceptions=True)`、末尾回填、设置 `image_notice`）使测试通过
- [x] 5.3 `backend/app/api/v1/routes/quiz.py`：`generate`/`generate_sync` 改为登录即取 `get_optional_user` 的 `user.id` 传入 `run_generation(..., user_id=...)`（知识库校验逻辑不变）；透传 `generate_images`；`backend/app/api/deps.py` 新增 `get_image_service` 单例；扩展 `backend/tests/test_api.py` 验证透传与匿名兼容
- [x] 5.4 `backend/app/services/record_service.py`：`submit` 写快照带 `image_url`、`_to_question_item` 回读 `image_url`；扩展 `backend/tests/test_records.py` 验证落库与详情回读保留配图

## 6. 后端全量回归

- [x] 6.1 `pytest tests/ -q`（沙箱加 `--basetemp=.tmp`）全绿，既有出题/研究/知识库/报告/用户链路零破坏

## 7. 前端

- [x] 7.1 `frontend/src/types/index.ts` 加 `Question.image_url`、`TaskState.image_notice`、`RecordQuestionItem.image_url`；`frontend/src/services/api.ts` 的 `submitQuizTask` 增加可选 `generate_images`；`npx tsc --noEmit` src 零错误
- [x] 7.2 `frontend/src/store/quiz.ts`：`QuizState` 加 `generateImages` 与 `setGenerateImages`；`hydrateRecord` 回填 `questions`（含 `image_url`，供历史回顾展示）
- [x] 7.3 `frontend/src/pages/index/index.tsx`：闯关设置区新增「生成图片」开关（仿 kb-sec，仅登录可见/可开；未登录点击引导登录），`go()` 透传 `generateImages` 到 `resetSession`/提交
- [x] 7.4 `frontend/src/pages/generating/index.tsx`：识别 `imaging` 阶段显示「配图生成中」文案；任务返回 `image_notice` 非空时以 Toast/提示条展示降级原因
- [x] 7.5 `frontend/src/pages/quiz/index.tsx`：题干卡片（stem-card）在 `question.image_url` 非空时渲染配图（`Image` 组件，加载失败隐藏），不影响判题
- [x] 7.6 新建 `frontend/src/pages/review`（`index.tsx`/`index.scss`/`index.config.ts`）：逐题展示题干、配图、选项、正确答案与讲解；`frontend/src/app.config.ts` 注册 `pages/review/index`；`frontend/src/pages/report/index.tsx` 增加「回顾题目」入口跳转 review（携带记录 id，经 `getQuizRecordDetail`+`hydrateRecord` 取题）
- [x] 7.7 `npm run build:weapp` 构建成功

## 8. 端到端验收

- [x] 8.1 后端干净环境真实端到端（MySQL 在线、配好百炼+COS、`image_gen_enabled=true`）：登录 → 勾选配图出题 → 题目 `image_url` 为 COS 永久 URL（可直接访问）→ 结算落库 → 历史详情回读含 `image_url`
- [x] 8.2 降级与限额验收：a) 未登录勾选配图 → 正常出题、无图、`image_notice` 提示登录；b) 未配 COS/密钥或 `image_gen_enabled=false` → 无图、任务不失败；c) 连续出题至当日 20 张后再出题 → 无图 + 额度用完提示，次日恢复
- [x] 8.3 微信开发者工具端到端：首页开关、generating 阶段文案与降级提示、答题页配图展示、report → review 历史回顾配图；`pytest` 全量回归通过（用户确认开发测试完成）
