# syntax=docker/dockerfile:1
# ============================================================
#  智趣 AI 闯关学习小程序 · 后端 —— 微信云托管 Dockerfile
# ------------------------------------------------------------
#  微信云托管规范（官方文档确认）：
#   1. 容器须监听 0.0.0.0；对外端口由控制台「服务设置 → 容器端口」决定，
#      默认 80，平台通过环境变量 PORT 注入（此处用 ${PORT:-80} 兼容）。
#   2. 仅最后一条 CMD 生效，遵循 Docker 官方规范。
#   3. 健康检查在控制台「服务设置 → 健康检查」配置，本项目路径为
#      /api/v1/health（端口与容器端口一致）。
#
#  构建上下文 = backend/ 目录；Dockerfile 路径 = backend/Dockerfile。
#  环境变量（DB_* / *_API_KEY / JWT_SECRET 等）在控制台注入，
#  切勿写入镜像（.dockerignore 已排除 .env）。
# ============================================================

########## 构建阶段：安装依赖到独立 venv ##########
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# 个别包若无预编译 wheel 需本地编译，构建期装齐工具链（不进入运行镜像）
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 先拷贝依赖清单再安装，充分利用镜像层缓存（改代码不重装依赖）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

########## 运行阶段：最小化镜像 ##########
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=80

WORKDIR /app

# 运行期系统库：
#  - ca-certificates：保证出站 HTTPS（DeepSeek / Tavily / 百炼 / COS / 微信）
#  - libgomp1：chromadb 依赖的 onnxruntime 运行所需
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段拷贝已安装好的依赖
COPY --from=builder /opt/venv /opt/venv

# 拷贝应用代码（.dockerignore 已排除 .venv / .env / 缓存 / 本地数据）
COPY app ./app

# 运行期可写目录：头像上传 / Chroma 持久化
# ⚠ 容器文件系统是临时的，重启或扩缩容都会丢失；正式环境请在云托管控制台
#   挂载持久存储（对象存储 / CBS），或：头像走 COS、任务状态走 Redis、
#   业务数据走 MySQL（DB_* 连接字段）。
RUN mkdir -p /app/uploads /app/kb_data

# EXPOSE 仅作声明；实际对外端口由「服务设置 → 容器端口」决定（建议填 80）
EXPOSE 80

# 单进程启动：本项目出题任务状态存于进程内存（task_store.py），
# 因此不可加 --workers，且建议「实例副本数」设为 1（多实例需先迁移到 Redis）。
# exec 让 uvicorn 成为 PID 1，正确接收平台下发的 SIGTERM 实现优雅退出。
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-80}"]
