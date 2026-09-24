# MemU MCP Server - 部署指南

本指南介绍如何在本地完整部署 MemU MCP Server：PostgreSQL + pgvector 存储层、memu-py 记忆引擎、以及本项目的 MCP 接口层。

## 目录结构

```
memu-mcp/
├── server.py           # MCP Server 核心实现（手写 JSON-RPC 协议层）
├── memu_utils.py       # MemU 辅助层（可直接调用）
├── __init__.py         # 包初始化
├── pyproject.toml      # 项目配置
├── requirements.txt    # Python 依赖
├── docs/
│   ├── INSTALL.md      # 本文件（部署指南）
│   └── QUICKREF.md     # 快速参考
└── README.md           # 使用文档
```

## 部署步骤

### 1. 安装 PostgreSQL + pgvector

```bash
# macOS
brew install postgresql@16 pgvector
brew services start postgresql@16
createdb memu

# Windows
# 下载安装 PostgreSQL（14+），并通过 SQL 启用 pgvector 扩展
```

在 memu 数据库中启用向量扩展：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 2. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

在 MemU 工作目录创建 `.env` 文件（server.py 启动时自动读取）：

```env
# LLM 与 Embedding 的 API Key（按 MemU 实际使用的服务配置）
DASHSCOPE_API_KEY=your_dashscope_api_key_here
VOYAGE_API_KEY=your_voyage_api_key_here

# 存储配置
DATABASE_TYPE=postgres
POSTGRES_DSN=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/memu
```

**获取 API Key**：
- 阿里云百炼（通义千问）：https://help.aliyun.com/zh/model-studio/developer-reference/get-api-key
- Voyage AI（Embedding）：https://docs.voyageai.com/

### 4. 接入 Claude Code

在 `.mcp.json` 中添加（stdio 模式）：

```json
{
  "mcpServers": {
    "memu": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/absolute/path/to/memu-mcp"
    }
  }
}
```

或以独立 HTTP 服务运行（可被 mcp-manager 等工具统一管理）：

```bash
python server.py --transport http --host 127.0.0.1 --port 3335
```

```json
{
  "mcpServers": {
    "memu": { "type": "http", "url": "http://127.0.0.1:3335/mcp" }
  }
}
```

### 5. 验证

```bash
# 健康检查（存储连接、API Key 有效性）
python memu_utils.py health

# 命令行快速验证记忆功能
python memu_utils.py save "这是一条测试记忆"
python memu_utils.py search "测试"
```

重启 Claude Code 后，对话中即可直接使用 `save_memory` / `search_memory` 等工具。

## 技术架构

```
Claude Code CLI
    ↓ (MCP 协议)
MCP Server (手写 JSON-RPC 协议层)
    ↓ (调用)
memu_utils (辅助层)
    ↓ (存储)
MemU (memu-py) + PostgreSQL + pgvector
```

**技术栈**：
- **MCP 协议**: Model Context Protocol
- **协议层**: 手写 MCP 协议（JSON-RPC 2.0，仅标准库）
- **记忆系统**: MemU (memu-py)
- **向量存储**: PostgreSQL + pgvector
- **Embedding**: Voyage AI voyage-4-lite（可替换）
- **LLM**: 通义千问 qwen-plus（可替换）

## 故障排查

1. **PostgreSQL 未运行**：`brew services list`（macOS）或服务管理器（Windows）确认状态
2. **API Key 无效**：检查 `.env` 配置，运行 `python memu_utils.py health` 看详细报错
3. **MCP 连不上**：查看 Claude Code 的 MCP 日志（`mcp-logs-memu/` 目录下的 stderr 输出）
4. **日志文件**：`logs/` 目录

## License

MIT
