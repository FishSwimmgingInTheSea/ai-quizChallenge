# Design

## Context

动机见 `proposal.md - Why`。当前出题链路（`QuizService.run_generation` / `generate_quiz_sync`）逐题生成并 `store.append_question` 边出边答，首题就绪即开答；异步任务经 `BackgroundTasks` + `TaskStore`（进程内、带 `threading.Lock`、TTL）驱动轮询。研究阶段已确立 `asyncio.to_thread` 下放阻塞调用的范式（见 `research_tools.py`）。题目快照由 `RecordService.submit` 写入 `quiz_record_items`（自包含题快照，options/answer 为 JSON 列）。DB 生产 MySQL、测试内存 SQLite，`init_db` 用 `create_all` 幂等建表。配置走 pydantic-settings（`config.py` + `.env`），异常统一 `AppException`（HTTP 200 + 业务 code）。依赖注入 + Protocol + Fake Mock 是既有 TDD 范式。

关键外部事实（已核实）：`qwen-image-2.0` 仅支持 DashScope `MultiModalConversation.call()` 同步接口，返回图片 URL **有效期仅 24 小时**，故必须下载转存；`dashscope`、`cos-python-sdk-v5` 均为新依赖，尚未安装；图片下载可复用已有 `httpx`。`create_all` 只建新表、不给已有表加列。

## Goals / Non-Goals

**Goals:**
- 配图作为出题的**可选旁路**，与既有链路解耦；默认关闭时零行为差异。
- 生图与上传全链路**失败即降级**，任何异常都不得冒泡到出题主流程。
- 并发为多题生图以压缩总等待；不破坏「首题就绪即开答」体验。
- 配额计数跨重启持久、并发原子、跨自然日自动恢复。
- 历史回看可复现当时配图（快照落库 `image_url`）。

**Non-Goals:**
- 不做图片内容审核 / NSFW 二次校验（依赖百炼模型自身策略）。
- 不做图片编辑、多图选择、用户自定义提示词。
- 不做 COS 私有桶签名 URL / CDN 自定义域名（本次用公有读桶 + 默认域名）。
- 不为匿名用户提供任何配图（含临时 URL 直出）。
- 不引入独立的生图后台队列 / 消息中间件（复用现有出题任务内的并发）。

## Decisions

### D1. 生图时机：题目产出后并发触发，出题末尾统一 await
在 `run_generation` 逐题循环中，每 `append_question` 后立即为该题 `create_task` 一个配图协程（受配额与开关约束）；所有题目生成完后 `asyncio.gather(..., return_exceptions=True)` 统一等待，再回填 `image_url` 并置 `done`。
- **理由**：并发压缩总耗时；`return_exceptions=True` 保证单题失败不牵连其他题与主流程。
- **备选**：串行生图（等待过久，弃）；出题前批量生图（题目尚未产出、无内容可依，弃）。
- **权衡**：配图 await 发生在全部题目就绪之后，故「边出边答」的首题开答不受影响；配图完成前该题 `image_url` 为空，前端轮询到题目即可先答、图后到。同步版 `generate_quiz_sync` 用 `asyncio.run` 内部同款并发。

### D2. 阶段可观测：新增 `imaging` phase
`TaskStore.set_phase` 增加 `imaging` 取值；仅当本次任务实际触发了配图协程时才进入。未开启配图永不进入该阶段，保持既有轮询语义。前端 `generating` 页据 phase 显示「配图生成中」。

### D3. 配额存储：DB 表 `image_gen_usage`，按 (user_id, date) 唯一行 + 原子自增
新增表 `image_gen_usage(id, user_id, usage_date, count)`，`UNIQUE(user_id, usage_date)`。`UsageService`（仿 `kb_service.process_document` 自建 session）：读取当日行 → 判断是否 `< limit` → 生图成功后 `count += 1`（`INSERT ... ON DUPLICATE KEY UPDATE count = count + 1` / SQLite `ON CONFLICT DO UPDATE`，或行级 `SELECT ... FOR UPDATE`）。
- **理由**：跨重启持久（进程内计数会丢）；DB 唯一约束 + 原子更新天然抗并发超发；跨自然日因 `usage_date` 不同自动开新行、配额自然恢复。
- **备选**：进程内 dict（重启丢失、多 worker 不共享，弃）；Redis（项目未引入，弃）。
- **权衡**：先判额度再生图、成功后才计数——生图失败不消耗额度；并发下可能极小概率略微少发（保守），可接受。

### D4. 永久存储：COS 公有读桶 + 默认域名 `get_object_url`
`cos_store.py` 封装 `CosConfig`(region, secret_id, secret_key) + `CosS3Client`；对象键 `quiz-images/{user_id}/{yyyymm}/{uuid}.{ext}`；`put_object` 上传字节流后用 `get_object_url(bucket, key)` 取公有读永久 URL。
- **理由**：用户已确认公有读桶 + 默认域名，最简。
- **备选**：私有桶 + 预签名 URL（有时效、需续签，弃）；自定义 CDN 域名（本次不引入）。

### D5. 生图封装：DashScope 同步接口 + `asyncio.to_thread` 下放
`image_gen.py` 用 `dashscope.MultiModalConversation.call(model="qwen-image-2.0", messages=[...], n=1, size="512*512", negative_prompt=...)`（同步阻塞），经 `asyncio.to_thread` 下放；解析返回取图片临时 URL，再用 `httpx` 下载为字节。定义 `ImageGenerator` Protocol 便于测试注入 Fake。
- **理由**：复用既有 `to_thread` 范式；Protocol + Fake 契合 TDD。
- **n>1 说明**：本设计按题独立生图（n=1）以便逐题回填与逐题降级；不采用单次多题合批（合批难以对应到题、且一失败全失败）。

### D6. 降级链路（全部静默、题目照常返回）
统一在 `image_service.generate_for_question(...) -> str | None` 收敛所有降级判断，返回 `None` 即不配图：
1. 配图总开关 `image_gen_enabled=false` → None
2. 未登录（无 user_id）→ None + `image_notice`=「登录后才能生成配图」
3. 未配 `dashscope_api_key` 或 COS 凭据 → None（记日志）
4. 当日额度已达上限 → None + `image_notice`=「今日配图额度已用完」
5. 生图 / 下载 / 上传异常或超时 → 该题 None（记日志）
`image_notice` 取本次任务**首个**非空提示（`TaskStore.set_image_notice` 幂等：已设则不覆盖），随 `TaskState` 返回。

### D7. 提示词构建：纯函数
`build_image_prompt(question) -> str`：以题干为核心，拼接知识点 / 正确选项语义，附固定风格后缀（简洁插画、无文字水印、白底、适合学习），并截断到 `image_prompt_max_len`。纯函数、无外部依赖，便于单测。

### D8. 数据结构与向后兼容
- `Question.image_url: str = ""`（默认空串，Pydantic 可选字段，旧前端忽略即可）。
- `GenerateQuizRequest.generate_images: bool = False`。
- `TaskState.image_notice: str = ""`。
- `RecordQuestionItem.image_url: str = ""`。
- ORM `QuizQuestionRecord` 加 `image_url VARCHAR(500) NOT NULL DEFAULT ''`；新增 `ImageGenUsage` 表。
所有新增字段均有默认值，序列化/反序列化对既有调用方零破坏。

### D9. user_id 透传
`/quiz/generate` 与 `/generate/sync` 当前仅在选知识库时经 `_validate_kb_selection` 得到 user_id。改为**登录即取** `get_optional_user` 的 `user.id` 传入 `run_generation(..., user_id=...)`，供配额归属与 COS 路径；未登录传 None。既有知识库校验逻辑不变（仍要求选库必登录）。

## Risks / Trade-offs

- **[MySQL 已有表加列]** `create_all` 不给 `quiz_record_items` 加 `image_url` 列 → **迁移**：需手动执行一次 `ALTER TABLE quiz_record_items ADD COLUMN image_url VARCHAR(500) NOT NULL DEFAULT '';`（新表 `image_gen_usage` 由 `create_all` 自动建）。测试用内存 SQLite 每次重建，不受影响。
- **[百炼模型权限]** `DASHSCOPE_API_KEY` 未必开通 `qwen-image-2.0` → 生图 4xx/5xx 时按 D6 第 5 条降级，题目照常返回，日志留痕；不阻塞。
- **[临时 URL 24h 过期]** 若只用临时 URL，历史回看会失效 → 强制走 D4 下载转存 COS，`image_url` 存永久 URL。
- **[并发超发额度]** 同用户并发出题可能竞争额度 → D3 用 DB 唯一约束 + 原子自增；先判后生、成功才计数，保守不超发。
- **[生图拖慢出题]** await 全部配图增加总时长 → D1 并发 + 超时（`image_gen_timeout`）；配图在题目全就绪后才 await，首题开答不受影响；超时即该题降级。
- **[COS 凭据泄露]** secret 从环境变量读取，绝不硬编码、不入库、不写日志 → 更新 `.env.example` 占位。
- **[新依赖体积]** `dashscope`、`cos-python-sdk-v5` 引入 → 均为官方 SDK，惰性导入（仅在配图路径 import），不影响未启用配图的启动。

## Migration Plan

1. 安装依赖：`pip install dashscope cos-python-sdk-v5`（写入 `requirements.txt`）。
2. 配置 `.env`：新增生图与 COS 项（见 tasks），`image_gen_enabled` 默认 `false`，未配置时全链路降级、对现网零影响。
3. 部署新代码：`create_all` 自动建 `image_gen_usage`。
4. **手动执行一次** MySQL `ALTER TABLE quiz_record_items ADD COLUMN image_url VARCHAR(500) NOT NULL DEFAULT '';`。
5. 灰度：先在 `.env` 配好百炼 + COS 凭据并将 `image_gen_enabled=true`，小流量验证生图/转存/配额；异常即置回 `false` 秒级回滚（无需回滚代码或数据）。
6. 回滚：关闭 `image_gen_enabled` 即停用配图；已写入的 `image_url` 为附加数据，不影响旧逻辑读取。

## Open Questions

- 配图默认分辨率固定 512×512；若后续需要按题型差异化尺寸，可在不改规格的前提下调整 `image_size` 配置（当前作为常量配置项，无阻塞）。
