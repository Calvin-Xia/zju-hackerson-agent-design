# 多阶段构建
# 阶段1：构建前端
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# 阶段2：Python 后端
FROM python:3.10-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖（先只复制依赖文件，利用镜像层缓存）
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY src/ ./src/

# 复制前端构建产物（由后端直接托管）
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 创建运行时数据目录（实际使用时由 docker-compose 挂载宿主机 ./data）
RUN mkdir -p data/textbooks data/knowledge_graphs data/vectorstore \
             data/embedding_cache data/tasks data/dialogue

EXPOSE 8001

# 健康检查：基础镜像里没有 curl，用 Python 标准库探测，避免探活永远失败
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=5).status == 200 else 1)"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
