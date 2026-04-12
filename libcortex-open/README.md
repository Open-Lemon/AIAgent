# DeepSeek 智能体开发实践

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![DeepSeek](https://img.shields.io/badge/Model-DeepSeek--V3-green.svg)](https://deepseek.com)

> 本书配套开源代码 · 模块化智能体开发实践

## 项目简介

本项目是一个基于 DeepSeek 大模型的模块化 AI 智能体（AI Agent）参考实现。本项目展示了如何将智能体系统解耦为**规划**（Planning）、**执行**（Execution）、**记忆**（Memory）和**总结**（Summarization）四个微服务模块，并通过统一的 Workflow 编排实现完整的智能体功能。

本项目的核心理念是**关注点分离**（Separation of Concerns），每个模块独立运行、通过 HTTP API 进行通信，便于开发、测试和部署。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        User / Client                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Workflow Orchestrator                     │
│  (workflow.py - 负责协调各模块，实现"规划 - 执行 - 观察"循环)     │
└─────────────────────────────────────────────────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   Planning    │ │   Execution   │ │   Session     │ │  Summarization│
│    Service    │ │    Service    │ │   Memory      │ │    Service    │
│  (Port 10000) │ │  (Port 15000) │ │  (Port 20000) │ │  (Port 25000) │
├───────────────┤ ├───────────────┤ ├───────────────┤ ├───────────────┤
│ • 任务分解    │ │ • 工具调用    │ │ • MongoDB     │ │ • 结果总结    │
│ • 意图识别    │ │ • 参数填充    │ │ • 会话存储    │ │ • 回复生成    │
│ • 工具选择    │ │ • MCP 服务集成  │ │ • 历史记录    │ │ • 格式化输出  │
└───────────────┘ └───────────────┘ └───────────────┘ └───────────────┘
         │              │
         ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Services                            │
│         ┌─────────────┐         ┌─────────────────────┐         │
│         │  DeepSeek   │         │  MCP Server         │         │
│         │  LLM API    │         │  (e.g., 高德地图)    │         │
│         └─────────────┘         └─────────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

### 模块说明

| 模块 | 端口 | 核心功能 |
|------|------|----------|
| **Planning** | 10000 | 接收用户查询，分析意图，分解任务步骤，选择合适的工具 |
| **Execution** | 15000 | 执行工具调用，处理参数填充，返回执行结果 |
| **Session Memory** | 20000 | 基于 MongoDB 的会话记忆存储，支持多轮对话上下文 |
| **Summarization** | 25000 | 汇总执行结果，生成符合人设的最终回复 |

## 快速开始

### 环境要求

- Python 3.10+
- MongoDB（Docker 或本地安装）
- DeepSeek API 密钥（或兼容的大模型服务）
- MCP 服务密钥（可选，用于工具调用）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置文件说明

项目使用 YAML 和 JSON 格式的配置文件，位于 `config/` 目录下：

| 文件 | 用途 |
|------|------|
| `config/resource.yml` | 配置大模型服务的 base_url、api_key 和 model |
| `config/mcp.json` | 配置 MCP 服务（如高德地图 API） |
| `config/docker-compose.yml` | MongoDB 的 Docker Compose 配置 |
| `config/session_memory.yml` | 会话记忆模块配置 |
| `config/planning.yml` | 规划模块配置 |
| `config/execution.yml` | 执行模块配置 |
| `config/summarizaztion.yml` | 总结模块配置 |

### 第一步：获取大模型服务

你可以选择以下任一方式：

1. **使用云服务**：注册 [DeepSeek](https://platform.deepseek.com/)、[阿里云百炼](https://bailian.console.aliyun.com/) 等平台获取 API 密钥
2. **私有化部署**：使用 vLLM 等框架在本地部署 DeepSeek-V3 模型

编辑 `config/resource.yml`，填写你的大模型服务信息：

```yaml
deepseek:
  base_url: "https://api.deepseek.com"  # 或你的私有部署地址
  api_key: "sk-your-api-key-here"       # 替换为你的 API 密钥
  model: "deepseek-v3"                  # 或 deepseek-chat / deepseek-coder
```

### 第二步：配置 MCP 服务（可选）

本项目示例使用 [高德地图 MCP 服务](https://mcp.amap.com/) 作为外部工具。

1. 访问高德开放平台注册并创建应用，获取 API Key
2. 编辑 `config/mcp.json`，将 `{your-key}` 替换为你的密钥：

```json
{
  "mcpServers": {
    "amap-maps": {
      "url": "https://mcp.amap.com/",
      "endpoint": "sse?key=your-actual-key-here",
      "type": "alimap",
      "enabled": true
    }
  }
}
```

### 第三步：安装 MongoDB

使用 Docker Compose 快速安装 MongoDB：

```bash
# 设置你的数据库密码
export MONGODB_PASSWORD="your-secure-password"

# 编辑 config/docker-compose.yml，将 {your-password} 替换为上面的密码
# 然后启动 MongoDB 容器
docker-compose -f config/docker-compose.yml up -d
```

编辑 `config/session_memory.yml`，更新 MongoDB 连接字符串：

```yaml
mongodb: "mongodb://root:your-secure-password@localhost:27017/agent"
```

### 启动服务

在四个独立的终端窗口中分别启动各模块：

```bash
# 终端 1 - 启动规划模块
python -m planning.run --config config/planning.yml --run.port 10000

# 终端 2 - 启动执行模块
python -m execution.run --config-path config/execution.yml --port 15000

# 终端 3 - 启动会话记忆模块
python -m memory.session.run --config config/session_memory.yml --port 20000

# 终端 4 - 启动总结模块
python -m summarization.run --config config/summarizaztion.yml --port 25000
```

### 运行智能体

启动所有服务后，在新的终端运行 Workflow 客户端：

```bash
python workflow.py --config workflow.yml
```

运行成功后，你将看到类似以下的交互界面：

```
<session-id>

User: 你好

User: 帮我查询一下北京市海淀区的天气
正在调用工具
<tool-calling-details>

Assistant: <AI 生成的回复>
```

输入 `exit`、`quit` 或 `bye` 退出交互。

## 项目结构

```
libcortex-open/
├── planning/           # 规划模块
│   ├── run.py          # 服务入口
│   ├── service.py      # 服务实现
│   ├── llm.py          # LLM 调用逻辑
│   └── template/       # Prompt 模板
├── execution/          # 执行模块
│   ├── run.py          # 服务入口
│   ├── service.py      # 服务实现
│   ├── builder/        # 工具构建器
│   └── prompt/         # Prompt 配置
├── memory/             # 记忆模块
│   ├── session/        # 会话记忆
│   └── system/         # 系统记忆
├── summarization/      # 总结模块
│   ├── run.py          # 服务入口
│   ├── service.py      # 服务实现
│   ├── llm.py          # LLM 调用逻辑
│   └── template/       # Prompt 模板
├── examples/           # 示例代码
├── utils/              # 工具函数
├── config/             # 配置文件
├── workflow.py         # Workflow 编排
├── workflow.yml        # Workflow 配置
└── requirements.txt    # Python 依赖
```

## 核心特性

- **模块化架构**：各模块独立部署，通过 HTTP API 通信，便于水平扩展
- **基于 libentry**：使用 [libentry](https://pypi.org/project/libentry/) 框架简化服务化开发
- **MCP 集成**：支持 Model Context Protocol，可轻松集成各种外部工具
- **长短期记忆**：基于 MongoDB 实现会话记忆，支持多轮对话上下文
- **迭代式执行**：支持"规划 - 执行 - 观察"的迭代循环，处理复杂多步骤任务

## 技术栈

- **Python 3.10+**
- **FastAPI / libentry** - 微服务框架
- **MongoDB** - 会话记忆存储
- **Pydantic** - 数据验证与序列化
- **Jinja2** - Prompt 模板引擎
- **httpx** - HTTP 客户端
- **Rich** - 终端美化输出

## 安全说明

- 请勿将包含真实 API 密钥的配置文件提交到版本控制系统
- 建议使用环境变量或密钥管理服务管理敏感配置
- 生产环境部署时，请确保 MongoDB 等服务的访问控制已正确配置

## 参考资源

- [DeepSeek 官方文档](https://platform.deepseek.com/docs)
- [libentry PyPI](https://pypi.org/project/libentry/)
- [高德地图 MCP 服务](https://mcp.amap.com/)
- [vLLM 推理框架](https://github.com/vllm-project/vllm)

## 许可证

Apache License 2.0

---

*本项目为一本书的配套开源代码，旨在展示模块化智能体开发的工程实践。*
