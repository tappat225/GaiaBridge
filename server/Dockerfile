FROM python:3.12-slim

# ============================================================
# Tencent Cloud environment — apt & pip use domestic mirrors
# ============================================================

# Debian apt → Aliyun mirror (newer Debian uses .sources format)
RUN sed -i 's|http://deb.debian.org|http://mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd --create-home --shell /bin/bash mcp

# Working directory
WORKDIR /app

# pip → Tsinghua mirror
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    && pip config set global.trusted-host pypi.tuna.tsinghua.edu.cn

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY server.py .

# Create workspace mount point
RUN mkdir -p /workspace && chown mcp:mcp /workspace

USER mcp
EXPOSE 8000

# Start MCP server (streamable HTTP mode)
CMD ["python", "server.py"]
