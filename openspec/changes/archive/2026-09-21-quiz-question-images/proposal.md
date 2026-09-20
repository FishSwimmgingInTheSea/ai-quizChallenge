# Proposal

## Why

现有出题链路只产出文字题目（题干、选项、讲解），缺少视觉辅助。大量学习场景（英语单词、历史、地理、动植物等）配上一张与题目内容相关的图片能显著提升记忆效果——例如刷英语单词时为单词配对应实物图。当前系统完全没有为题目配图的能力。

阿里云百炼 `qwen-image-2.0` 文生图模型可复用项目已有的 `DASHSCOPE_API_KEY`，同步接口一次请求即可拿到图片；配合腾讯云 COS 对象存储把 24 小时临时图转为永久可访问 URL，即可以最小架构代价为题目加上配图能力。

## What Changes

- **出题可选配图**：出题请求新增可选开关 `generate_images`；勾选后系统在生成每道题的同时并发生成一张与题目内容相关的配图，回填到题目的 `image_url` 字段。
- **百炼 qwen-image-2.0 同步生图**：复用已有百炼 API Key，通过 DashScope `MultiModalConversation` 同步接口按题目内容自动构建提示词生图（512×512），并发调用降低总等待时间。
- **腾讯云 COS 永久存储**：生图得到的 24 小时临时 URL 立即下载并上传至 COS（公有读桶），换取永久可访问 URL 存入题目数据。
- **每人每日生图限额**：默认每人每天 20 张，DB 持久化按用户按日计数；额度用尽时降级为不配图并给出友好提示，不阻塞出题。
- **必须登录**：配图能力仅对已登录用户开放；匿名请求勾选配图时静默降级为不配图并提示登录。
- **失败静默降级**：未配置密钥 / 开关关闭 / 生图失败 / 上传失败 / 超时等一切异常，均降级为「题目正常返回、只是不带图」，绝不影响出题主流程。
- **历史记录回看配图**：题目快照新增 `image_url`，结算落库；新增「题目回顾」界面，实时局与历史回看均可逐题查看题干、配图、选项与讲解。
- **前端设置开关**：闯关设置页新增「生成图片」开关（未登录点击引导登录）；答题页与回顾页展示配图。
- **新增依赖与配置**：新增 `dashscope`、`cos-python-sdk-v5`，以及生图与 COS 相关配置项。

## Capabilities

### New Capabilities

- `question-images`: 题目 AI 配图能力——按题目内容构建生图提示词、百炼 qwen-image-2.0 同步生图、COS 永久存储、每人每日限额与用量计数、必须登录、生图/上传失败静默降级、配图 URL 随题目结构与历史记录持久化。

### Modified Capabilities

- `quiz-generation`: 出题请求新增可选 `generate_images` 开关；勾选后出题链路在生成题目的同时并发为每题生成配图并回填 `image_url`；任务阶段可观测性新增「配图生成中」；题目对外结构新增可选 `image_url` 字段，未勾选配图时链路与既有行为逐字一致、对现有前端完全向后兼容。

## Impact

- **后端代码**：
  - 新增 `app/llm/image_gen.py`（DashScope `qwen-image-2.0` 同步生图封装 + httpx 下载图片字节，`ImageGenerator` Protocol 可注入）
  - 新增 `app/services/cos_store.py`（腾讯云 COS `qcloud_cos` 封装：`put_object` + 公有读 `get_object_url`，`ImageStore` Protocol 可注入）
  - 新增 `app/services/image_service.py`（提示词构建纯函数 + 生图/上传/配额编排，一切失败降级返回 None）
  - 新增 `app/services/usage_service.py`（每人每日生图用量计数，DB 支撑、自建 session、原子自增）
  - `app/db/orm_models.py`：新增 `image_gen_usage` 表；`quiz_record_items` 新增 `image_url` 列
  - `app/models/quiz.py`：`Question` 加 `image_url`、`GenerateQuizRequest` 加 `generate_images`、`TaskState` 加 `image_notice`
  - `app/models/user.py`：`RecordQuestionItem` 加 `image_url`
  - `app/services/quiz_service.py`：出题编排并发生成配图、回填 `image_url`、降级提示、新增 `imaging` 阶段
  - `app/services/task_store.py`：`set_question_image` / `set_image_notice`
  - `app/services/record_service.py`：结算写入与详情回读 `image_url`
  - `app/api/v1/routes/quiz.py`：登录即向 `run_generation` 传 `user_id`（供配额归属）
  - `app/api/deps.py`：`get_image_service` 单例注入
  - `app/core/config.py` / `.env.example`：生图与 COS 配置项
- **前端代码**：`types/index.ts` 加 `image_url`/`image_notice`；`store/quiz.ts` 加 `generateImages` 与 setter、`hydrateRecord` 回填 questions；`services/api.ts` `submitQuizTask` 加 `generate_images`；首页「生成图片」开关；`generating` 页配图文案与提示；`quiz` 页题干配图；新增 `pages/review` 题目回顾页并在 `app.config.ts` 注册、报告页加入口
- **依赖**：`requirements.txt` 新增 `dashscope`、`cos-python-sdk-v5`（图片下载复用已有 `httpx`）
- **外部服务**：阿里云百炼 `qwen-image-2.0`（复用 `DASHSCOPE_API_KEY`，需开通该模型权限）；腾讯云 COS（公有读桶）
- **数据库**：新增 `image_gen_usage` 表（`init_db` 幂等建表）；`quiz_record_items` 新增 `image_url` 列需**手动执行一次 ALTER**（`create_all` 不给已有表加列）
- **测试**：提示词构建、生图封装（Mock dashscope+httpx）、COS 封装（Mock qcloud_cos）、image_service 降级、每日配额计数与跨天重置、quiz_service 配图编排与失败降级、路由透传与落库回读；全量回归不破坏既有用例
- **零影响保证**：`generate_images=false`（默认）或未登录时，出题链路、研究智能体、题目结构对外行为与改造前逐字一致（`image_url` 默认空串，现有前端无需修改）
