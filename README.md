# 智趣 AI 闯关学习小程序 · MVP

「万物皆可闯关」——输入一句话，AI 自动出题，逐题闯关 + 即时讲解，通关生成 AI 复盘报告与分享海报。

- 前端：**Taro 4.2.1 + React 18 + TypeScript**（微信小程序）
- 后端：**FastAPI + LangChain + DeepSeek（OpenAI 兼容）+ Pydantic v2**
- 核心闭环：`输入 → AI 出题(异步轮询) → 答题即时反馈 → 复盘报告 → 分享海报`

> 完整方案见 `docs/`，UI 原型见 `prototypes/`。前端 UI 严格 1:1 还原原型 v1.2。

---

## 目录结构

```
ai-quizChallenge/
├─ backend/            FastAPI 后端（TDD，43 个测试）
│  ├─ app/
│  │  ├─ api/          接口层（health / quiz / report + 统一响应）
│  │  ├─ core/         配置 / 异常 / 日志
│  │  ├─ models/       领域模型（Quiz/Question/Report…）
│  │  ├─ llm/          LangChain 工厂 + 出题链 + 报告链 + 输出 Schema
│  │  ├─ prompts/      版本化 Prompt
│  │  ├─ services/     出题/评分/报告服务 + 进程内任务存储
│  │  └─ utils/        清洗 / 敏感词 / ID
│  └─ tests/           pytest 全程 mock LLM，不消耗额度
├─ frontend/           Taro 小程序（S1–S10 十屏）
│  └─ src/
│     ├─ pages/        login / index / generating / quiz / report / poster / profile
│     ├─ components/   Mascot（小智 5 表情）
│     ├─ store/        Zustand 会话状态 + 本地判题
│     └─ services/     请求封装 / API / 轮询 / 本地存储
├─ docs/               需求 + 方案设计
└─ prototypes/         UI 原型（设计规范 + 核心流程）
```

---

## 一、后端启动

### 1. 安装依赖

```bash
cd backend
python -m venv .venv
# Windows
.venv/Scripts/python.exe -m pip install -r requirements.txt
# macOS/Linux
# source .venv/bin/activate && pip install -r requirements.txt
```

### 2. 配置 DeepSeek Key

复制 `.env.example` 为 `.env`，填入你的真实 Key：

```
DEEPSEEK_API_KEY=sk-你的真实key
```

> 在 https://platform.deepseek.com 申请。未填真实 Key 时，出题接口会返回 `code:5001` 的友好错误（链路本身正常，仅缺 Key）。

### 3. 运行测试（TDD）

```bash
.venv/Scripts/python.exe -m pytest
# 43 passed
```

### 4. 启动服务

```bash
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

- 健康检查：http://127.0.0.1:8000/api/v1/health
- 交互式文档：http://127.0.0.1:8000/docs

### 接口一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET  | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/quiz/generate` | 提交出题任务，返回 `task_id` |
| GET  | `/api/v1/quiz/task/{task_id}` | 轮询出题进度 |
| POST | `/api/v1/quiz/generate/sync` | 同步一次性出题（调试用） |
| POST | `/api/v1/report/generate` | 生成复盘报告 |

统一响应：`{ "code": 0, "message": "ok", "data": ... }`（非 0 即错误）。

---

## 二、前端启动（微信开发者工具）

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 编译小程序

```bash
npm run dev:weapp    # 开发（watch）
# 或 npm run build:weapp  # 生产构建
```

### 3. 用微信开发者工具打开

1. 打开「微信开发者工具」→ 导入项目，目录选择 `frontend/`（会读取 `frontend/project.config.json`，产物在 `frontend/dist`）。
2. AppID 选择「测试号」即可。
3. 在「详情 → 本地设置」勾选 **不校验合法域名**（本地直连 `http://127.0.0.1:8000`）。
4. 后端 API 地址在 `frontend/src/services/config.ts` 的 `API_BASE`，默认 `http://127.0.0.1:8000/api/v1`。

---

## 三、MVP 范围与说明

- ✅ 核心闭环全部接真实后端：首页输入 → 异步出题轮询 → 单选/多选/判断答题 → 即时对错讲解 → AI 复盘报告 → Canvas 分享海报。
- ✅ 前端本地判题（方案 §9.2），XP / 连击 / 分段进度 / 反馈抽屉 / 小智表情。
- ⏳ 登录（S1）、「我的」、最近闯关：按方案 §2.3 后置，当前用**本地 mock + 本地存储**占位。
- ⏳ 分享海报的小程序码为占位图（真实 wxacode 需 appid + 已备案后端）。

### 已知的与原型的合理偏差
- 顶部状态栏时间（原型的「9:41」）由真机系统提供，未在页面内重绘。
- 底部 TabBar 图标使用微信原生文字 Tab（未内置二进制图标资源）。
