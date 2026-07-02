# CapOwn

[English](README.md) | 中文

多主机远程操作与 AI Agent 协调系统。中央 Master 节点通过 HTTPS + SSE 管理并调度任务至多个 Worker 节点，实现跨网络执行，Worker 无需开放入站端口。

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
- **双部署模式**: Worker 支持容器 (Docker) 与宿主机 (原生) 两种部署模式。容器模式将用户选择的宿主机目录挂载为 Worker 工作区；宿主机模式直接在宿主机上执行命令。

### 组件

| 组件 | 职责 |
|---|---|
| **Master** | 节点注册表、SSE 代理、任务路由、认证网关 |
| **Worker** | 轻量守护进程，连接 Master、执行任务、上报结果 |
| **Client** | CLI 工具或 SDK，向 Master 调度任务 |

## 目录结构

```
CapOwn/
├── deploy.py                       # 统一交互式部署脚本 (菜单驱动)
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
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── config.toml.example
├── worker/                         # Worker: 执行面
│   ├── daemon.py                   #   主进程 (注册 + SSE 监听 + 重连)
│   ├── reporter.py                 #   结果上报 (POST 回 Master)
│   ├── executor/
│   │   ├── base.py                 #   抽象执行器接口
│   │   ├── shell.py                #   Shell 命令执行器
│   │   ├── file.py                 #   文件读写/列表执行器
│   │   └── system_info.py          #   系统信息执行器 (无需 Shell)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── requirements.txt
│   └── config.toml.example
├── client/                         # Client: CLI 客户端
│   ├── capown_client.py
│   └── config.ini.example
├── docs/
│   ├── deploy.md                   # 部署指南 (英文)
│   └── user_guide.md               # 使用指南 (英文)
├── README.md
├── README_zh.md
├── agent.md
└── .gitignore
```

## 快速部署

```bash
cd CapOwn/
python3 deploy.py
```

部署脚本完全菜单驱动，引导完成 Master、Worker 或两者的配置。完整部署指南（包括 Nginx 配置、构建参数、镜像选择及故障排查）见 [docs/deploy.md](docs/deploy.md)。

## 快速使用

```bash
# 列出已注册的 Worker
python client/capown_client.py nodes

# 在指定 Worker 上执行 Shell 命令
python client/capown_client.py run worker-1 "uname -a"
```

完整使用指南（包括配置说明、所有 CLI 命令、直接 API 调用、错误码及能力词汇表）见 [docs/user_guide.md](docs/user_guide.md)。

## 贡献

欢迎提交 Issue 或 Pull Request。

## License

CapOwn 使用 open-core 授权模式：

- `client/`、`worker/`、`shared/`、`docs/`、部署工具和根目录项目文件使用 Apache-2.0。
- `master/` 是 Community Master，使用 AGPL-3.0-only。
- 商业 Master 管理系统、Hosted 服务、计费、租户管理、区域中继、企业策略和相关云服务功能会在独立闭源商业条款下开发和分发。

详见 [LICENSE](LICENSE)。
