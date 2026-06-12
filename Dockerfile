FROM python:3.11-slim

WORKDIR /app

# 换用阿里云 Debian 源（加速国内构建）
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources

# 安装系统依赖（matplotlib 需要）
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# 使用代理加速下载（国内环境）
RUN pip install --no-cache-dir --proxy http://203.0.113.10:7890 -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

# 数据目录
RUN mkdir -p /data

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]