# L15: 镜像应 pin digest 以保证供应链可重现与防篡改.
# 推荐: FROM python:3.11-slim@sha256:<digest>  # 用 docker pull python:3.11-slim 后 docker inspect --format='{{.RepoDigests}}' 获取
# 此处保留 tag 形式, 待 CI/运维补全真实 digest 后替换 (不要编造 digest).

# ===== M39: builder 阶段 (含编译器, 不进入最终镜像) =====
FROM python:3.11-slim AS builder

WORKDIR /app

# 换用阿里云 Debian 源（加速国内构建）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 安装编译工具 (仅 builder 阶段, runtime 不继承)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# H13: 代理走 build-arg, 不传 = 不走代理 (CI/外部环境直接 build).
# 用 shell if 防止 --proxy= 空串触发 pip 报错
ARG HTTP_PROXY=
COPY requirements.txt .
# --user 装到 /root/.local, 供 runtime 阶段整目录拷走
RUN if [ -n "$HTTP_PROXY" ]; then \
      pip install --no-cache-dir --user --proxy="$HTTP_PROXY" \
        -i https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com \
        -r requirements.txt; \
    else \
      pip install --no-cache-dir --user \
        -i https://mirrors.aliyun.com/pypi/simple/ \
        --trusted-host mirrors.aliyun.com \
        -r requirements.txt; \
    fi
# H13: 末尾再次声明以清空默认值, 避免泄漏到后续层 / 镜像元数据
ARG HTTP_PROXY=

# ===== M39: runtime 阶段 (不含编译器, 减小体积与攻击面) =====
FROM python:3.11-slim AS runtime

WORKDIR /app

# 换用阿里云 Debian 源（加速国内构建）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 仅装运行时依赖: libgomp1 (numpy/scipy OpenMP), curl (HEALTHCHECK).
# 注意: 不装 gcc / g++ / build-essential —— 编译产物已在 builder 阶段完成.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 拷走 builder 装好的 pip --user 包 (整目录 /root/.local)
COPY --from=builder /root/.local /root/.local
# /root 默认 0700, 非 root 用户无法 traverse; 放开 x 位让 trendrod 可访问 .local
RUN chmod a+x /root && chmod -R a+rX /root/.local
# PATH 含 /root/.local/bin (uvicorn 等入口脚本); PYTHONUSERBASE 让 trendrod 用户能 import /root/.local 下的包
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUSERBASE=/root/.local

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
