FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # 阿里云 FC 容器 HTTP 默认端口
    PORT=9000

WORKDIR /code

# 安装系统依赖（pdfplumber 解析 PDF 可能用到）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        libffi-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg-dev \
        zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# 再复制项目代码
COPY . .

# 对外暴露给本地/调试使用；在 FC 中端口由环境变量约定为 9000
EXPOSE 9000

# 在容器中启动 WSGI 服务，供阿里云 FC 调用
# app:app 表示 app.py 里的 Flask 实例名为 app
CMD ["gunicorn", "-b", "0.0.0.0:9000", "app:app"]

