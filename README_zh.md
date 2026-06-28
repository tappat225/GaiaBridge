# WorkBridge

[English](README.md) | 中文

多主机远程操作与 AI Agent 协调系统。中央 Master 节点通过 HTTPS + SSE 管理并调度任务至多个 Worker 节点，实现跨网络执行，Worker 无需开放入站端口。

## 目录结构

```
WorkBridge/
├── shared/                         # 共享协议与工具
│   ├── protocol.py                 #   Pydantic 数据模型 (Node, Task, SSEEvent, 枚举)
│   ├── auth.py                     #   Token 生成与验证
│   └── config.py                   #   MasterConfig / WorkerConfig 配置模式
├── master/                         # Master: 中央控制面
│   ├── app.py                      #   Starlette 应用入口
│   ├── registry.py                 #   节点注册表 (SQLite)
│   ├── broker.py                   #   SSE 连接池管理器
│   ├── router.py                   #   任务调度与 Future 匹配
│   ├── auth.py                     #   Bearer Token 中间件
│   ├── api/
│   │   ├── nodes.py                #   节点注册/心跳/列表/SSE
│   │   └── tasks.py                #   任务调度/结果端点
│   ├── deploy.py                   #   跨平台部署脚本
│   ├── Dockerfile                  #   容器镜像
│   ├── docker-compose.yml          #   一键启动
│   ├── requirements.txt            #   Python 依赖
│   └── config.toml.example         #   配置模板
├── worker/                         # Worker: 执行面
│   ├── daemon.py                   #   主进程 (注册 + SSE 监听 + 重连)
│   ├── reporter.py                 #   结果上报 (POST 回 Master)
│   ├── executor/
│   │   ├── base.py                 #   抽象执行器接口
│   │   ├── shell.py                #   Shell 命令执行器
│   │   └── file.py                 #   文件读写/列表执行器
│   ├── deploy.py                   #   跨平台部署脚本
│   ├── Dockerfile                  #   容器镜像
│   ├── docker-compose.yml          #   一键启动
│   ├── requirements.txt            #   Python 依赖
│   └── config.toml.example         #   配置模板
├── client/                         # Client: CLI 客户端
│   ├── workbridge_client.py        #   命令行客户端
│   └── config.ini.example          #   配置模板
├── README.md
├── README_zh.md
├── agent.md
└── .gitignore
```

## 架构

```
[Client / Agent]
    | (HTTPS POST: 调度任务)
    v
[Master (公网 IP) -- 中央路由]
    ^ (HTTPS POST: 上报结果)
    | (SSE 长连接: 推送任务指令)
    |
    +-- [Worker @ 节点 A]
    +-- [Worker @ 节点 B]
    +-- [Worker @ 节点 C]
    ...
```

### 设计约束

- **全出站连接**: Worker 仅需出站 HTTPS，无需开放入站端口。
- **中央路由枢纽**: 所有节点间通信均通过 Master 路由。
- **能力/智能分离**: Worker 负责执行；Agent 负责 LLM 决策。
- **容器沙箱**: 所有节点在 Docker 中运行，限制文件系统访问。

### 组件

| 组件 | 职责 |
|---|---|
| **Master** | 节点注册表、SSE 代理、任务路由、认证网关 |
| **Worker** | 轻量守护进程，连接 Master、执行任务、上报结果 |
| **Client** | CLI 工具或 SDK，向 Master 调度任务 |

## 快速开始

### 1. 部署 Master (公网 IP 服务器)

```bash
cd master/
cp config.toml.example config.toml
# 编辑 config.toml: 设置 auth.node_token 和 auth.client_token
# 生成 token: python3 -c "import secrets; print(secrets.token_hex(32))"

# 默认部署
python3 deploy.py

# 使用国内镜像
python3 deploy.py --cn
```

Master 监听 `127.0.0.1:9210`，通过 Nginx 反向代理暴露 HTTPS。

### 2. 配置 Nginx

将以下配置合并到 HTTPS server 块中 (参见 `master/nginx.conf.example`):

```nginx
location /wb/ {
    proxy_pass http://127.0.0.1:9210/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # SSE 需要关闭缓冲
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

重载: `sudo nginx -t && sudo systemctl reload nginx`

### 3. 部署 Worker (任意节点)

```bash
cd worker/
cp config.toml.example config.toml
# 编辑 config.toml: 设置 worker.node_id, worker.master_url, auth.node_token
# node_token 需与 Master 配置一致
# 设置 deployment.host_workspace 为宿主机上的绝对工作路径

# 默认部署
python3 deploy.py

# 使用国内镜像
python3 deploy.py --cn
```

Worker 以出站方式连接 Master 并等待任务。

默认情况下，任务在容器内的 `/workspace` 下执行。部署脚本读取 `config.toml` 中的 `deployment.host_workspace`，将宿主机路径挂载到 `worker.workspace`：

```bash
python3 deploy.py
```

如直接使用 Docker Compose，设置 `WORKBRIDGE_HOST_WORKSPACE` 为宿主机路径，并保持 `WORKBRIDGE_CONTAINER_WORKSPACE` 与 `worker.workspace` 一致：

```bash
DOCKER_BUILDKIT=0 \
WORKBRIDGE_HOST_WORKSPACE=/home/ubuntu/repo \
WORKBRIDGE_CONTAINER_WORKSPACE=/workspace \
docker compose up -d
```

### 4. 同机部署 Master + Worker

当 Master 和 Worker 在同一台机器上时，Worker 直接指向 localhost 以避免 SSE 流经公网的问题：

```toml
# worker/config.toml
master_url = "http://127.0.0.1:9210"
```

### 5. 调度任务

```bash
# 通过 Nginx 代理 (外部客户端):
curl -X POST https://<master-domain>/wb/api/tasks/dispatch \
  -H "Authorization: Bearer <client-token>" \
  -H "Content-Type: application/json" \
  -d '{"target_node": "worker-1", "payload": {"task_type": "shell", "params": {"command": "uname -a"}}}'

# 或直连 Master 端口 (本地):
curl -X POST http://127.0.0.1:9210/api/tasks/dispatch \
  -H "Authorization: Bearer <client-token>" \
  -H "Content-Type: application/json" \
  -d '{"target_node": "worker-1", "payload": {"task_type": "shell", "params": {"command": "uname -a"}}}'
```

## API 端点

| 方法 | 路径 | 认证 | 描述 |
|---|---|---|---|
| POST | `/api/nodes/register` | Node Token | 注册 Worker 节点 |
| POST | `/api/nodes/heartbeat` | Node Token | 更新节点心跳 |
| GET | `/api/nodes` | - | 列出所有已注册节点 |
| GET | `/api/events?node_id=X` | Node Token | Worker 的 SSE 事件流 |
| POST | `/api/tasks/dispatch` | Client Token | 调度任务 (异步) |
| POST | `/api/tasks/dispatch_sync` | Client Token | 调度任务并等待结果 |
| POST | `/api/tasks/result` | Node Token | Worker 上报任务结果 |
| GET | `/api/tasks/{task_id}` | - | 获取任务结果 |
| GET | `/health` | - | 健康检查 |

## 配置

配置默认从本地文件加载。环境变量作为覆盖层，用于容器编排和密钥注入。

加载顺序：

```text
环境变量 > 配置文件 > 默认值
```

### Master (`master/config.toml`)

| TOML 键 | 环境变量覆盖 | 默认值 | 描述 |
|---|---|---|---|
| `master.host` | `MASTER_HOST` | `0.0.0.0` | 绑定地址 |
| `master.port` | `MASTER_PORT` | `9210` | 监听端口 |
| `auth.node_token` | `NODE_TOKEN` | (必填) | Worker 认证 Token |
| `auth.client_token` | `CLIENT_TOKEN` | (必填) | Client/Agent 认证 Token |
| `master.heartbeat_timeout` | `HEARTBEAT_TIMEOUT` | `60` | 心跳超时秒数 |
| `master.db_path` | `MASTER_DB` | `/app/data/registry.db` | SQLite 数据库路径 |

Master 容器读取 `/etc/workbridge/master.toml`；Compose 文件自动挂载 `master/config.toml` 到该路径。

### Worker (`worker/config.toml`)

| TOML 键 | 环境变量覆盖 | 默认值 | 描述 |
|---|---|---|---|
| `worker.node_id` | `NODE_ID` | (必填) | Worker 唯一标识 |
| `worker.master_url` | `MASTER_URL` | `https://localhost:9210` | Master 端点 URL |
| `auth.node_token` | `NODE_TOKEN` | (必填) | 认证 Token (需与 Master 一致) |
| `worker.workspace` | `WORKSPACE_DIR` | `/workspace` | 容器内工作目录 |
| `worker.command_timeout` | `COMMAND_TIMEOUT` | `120` | Shell 命令超时秒数 |
| `worker.reconnect_interval` | `RECONNECT_INTERVAL` | `5` | 重连间隔秒数 |
| `deployment.host_workspace` | - | (`deploy.py` 必填) | 挂载到 `worker.workspace` 的宿主机路径 |

Worker 容器读取 `/etc/workbridge/worker.toml`；Compose 文件自动挂载 `worker/config.toml` 到该路径。

### Client (`client/config.ini`)

Client 使用 INI 格式以兼容旧版 Python 无需额外依赖。自动读取 `client/config.ini`，或通过 `--config` / `WORKBRIDGE_CLIENT_CONFIG` 指定路径。

| INI 键 | 环境变量覆盖 | 默认值 | 描述 |
|---|---|---|---|
| `client.master_url` | `MASTER_URL` | `https://<your-domain>/wb` | Master API 基础 URL |
| `client.client_token` | `CLIENT_TOKEN` | (必填) | Client Bearer Token |
| `client.timeout` | `CLIENT_TIMEOUT` | `120` | 同步任务超时秒数 |

## 构建系统

### Docker 构建要求

在 Docker 默认桥接网络无 DNS 解析的机器上 (常见于云服务器)，以下两个标志为**必需**：

| 标志 | 原因 |
|---|---|
| `DOCKER_BUILDKIT=0` | BuildKit 的 `--network=host` 不可靠；传统构建器可正常传递宿主机网络 |
| `--network=host` | 让构建容器使用宿主机网络栈，使 `apt-get` 和 `pip` 能访问外部仓库 |

### ARG 作用域 (Dockerfile)

`FROM` 之前声明的 ARG 仅在 `FROM` 指令中可见。若要在 `RUN` 步骤中使用，需在 `FROM` 之后重新声明：

```dockerfile
ARG APT_MIRROR=deb.debian.org
FROM ${PYTHON_IMAGE}
ARG APT_MIRROR          # 重新声明以引入作用域
RUN sed -i "s|http://deb.debian.org|http://${APT_MIRROR}|g" ...
```

### 镜像配置

| 构建参数 | 默认值 (国际) | 国内示例 |
|---|---|---|
| `PYTHON_IMAGE` | `python:3.12-slim` | (保持默认) |
| `APT_MIRROR` | `deb.debian.org` | `mirrors.tuna.tsinghua.edu.cn` |
| `PIP_INDEX_URL` | `https://pypi.org/simple` | `https://pypi.tuna.tsinghua.edu.cn/simple` |

切换国内镜像：

```bash
python3 deploy.py --cn
```

## 安全

- **双 Token 机制**: Node Token (Worker 身份) 与 Client Token (调度权限) 分离
- **全出站网络**: Worker 不暴露入站端口
- **路径遍历拦截**: 所有文件操作通过 realpath 验证强制限制在工作目录内
- **容器隔离**: Master 和 Worker 均以非 root 用户在 Docker 中运行
- **命令超时**: 长时间运行的命令自动终止
- **无硬编码密钥**: Token 从本地配置文件或环境变量加载
- **Master 仅本地监听**: Master 绑定 127.0.0.1，仅通过 Nginx 反向代理暴露

## 故障排查

### 构建报 "Undetermined Error" (apt-get)

构建容器无法访问 Debian 仓库。三种解决方案：

1. 使用 `DOCKER_BUILDKIT=0 docker build --network=host`
2. 通过 `--build-arg APT_MIRROR=...` 使用就近镜像
3. 确认 `APT_MIRROR` 在 Dockerfile 中 `FROM` 之后重新声明

### Worker 无法连接 Master

- 验证 Master 可达: `curl <MASTER_URL>/health`
- 检查 `NODE_TOKEN` 与 Master 配置是否一致
- 确保防火墙未阻止出站 HTTPS

### 任务已调度但无结果

- 检查目标 Worker 是否在线: `GET /api/nodes`
- 确认 Worker SSE 连接活跃
- 查看 Worker 日志: `docker compose logs worker`
- **SSE 换行符**: 守护进程必须使用 `\r\n\r\n` 作为事件分隔符
- **同机 Worker**: 优先使用 `master_url = "http://127.0.0.1:9210"`

## License

[MIT](LICENSE)