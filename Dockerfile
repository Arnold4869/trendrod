FROM python:3.11-slim

WORKDIR /app

# 换用阿里云 Debian 源（加速国内构建）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖（matplotlib 需要）+ curl 用于 HEALTHCHECK
# M36: --no-install-recommends 缩小镜像 + 减攻击面
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# H13: 代理走 build-arg, 不传 = 不走代理 (CI/外部环境直接 build).
# 用 shell if 防止 --proxy= 空串触发 pip 报错
ARG HTTP_PROXY=
COPY requirements.txt .
RUN if [ -n "$HTTP_PROXY" ]; then \
      pip install --no-cache-dir --proxy="$HTTP_PROXY" \
        -i https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com \
        -r requirements.txt; \
    else \
      pip install --no-cache-dir \
        -i https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com \
        -r requirements.txt; \
    fi
# H13: 末尾再次声明以清空默认值, 避免泄漏到后续层 / 镜像元数据
ARG HTTP_PROXY=

COPY app/ ./app/
COPY static/ ./static/

# 数据目录
RUN mkdir -p /data

# H14: 以非 root 用户运行
RUN useradd -m -s /bin/bash trendrod
USER trendrod

# M37: 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]