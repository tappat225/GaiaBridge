FROM python:3.12-slim

# ============================================================
# 腾讯云环境 — apt & pip 全部走国内镜像
# ============================================================

# Debian apt → 阿里云镜像（新版 Debian 用 .sources 格式）
RUN sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户
RUN useradd --create-home --shell /bin/bash mcp

# 工作目录
WORKDIR /app

# pip → 清华源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY server.py .

# 创建 workspace 挂载点
RUN mkdir -p /workspace && chown mcp:mcp /workspace

USER mcp
EXPOSE 8000

# 启动 MCP server（streamable HTTP 模式）
CMD ["python", "server.py"]
