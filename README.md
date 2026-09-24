# MemU MCP Server

为 Claude Code CLI 提供 MemU 记忆系统的 MCP (Model Context Protocol) 接口。

[English](README_EN.md) | [简体中文](README.md)

## 功能特性

- **保存记忆** - 将重要信息保存到记忆系统
- **语义搜索** - 使用自然语言查询相关记忆
- **上下文检索** - 智能获取会话相关的历史记忆
- **统计信息** - 查看记忆系统的使用情况

## 架构

```
Claude Code CLI
    ↓ (MCP 协议)
MCP Server (工具层)
    ↓ (调用)
memu_utils (辅助层)
    ↓ (存储)
MemU Service + PostgreSQL + pgvector
```

## 安装

### 1. 安装依赖

```bash
# 使用 pip
pip install -r requirements.txt

# 或使用 uv（推荐）
uv pip install -r requirements.txt
```

### 2. 配置环境变量

在 MemU 工作目录创建 `.env` 文件（启动时自动读取），包含以下配置：

```env
# 通义千问 LLM 配置
DASHSCOPE_API_KEY=your_dashscope_api_key

# PostgreSQL 配置
DATABASE_TYPE=postgres
POSTGRES_DSN=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/memu
```

### 3. 配置 MCP Server

在 `.mcp.json` 中添加：

```json
{
  "mcpServers": {
    "memu": {
      "type": "stdio",
      "command": "python",
      "args": ["server.py"],
      "cwd": "/absolute/path/to/memu-mcp"
    }
  }
}
```

> 也可以独立 HTTP 服务运行：`python server.py --transport http --host 127.0.0.1 --port 3335`，然后配置 `"type": "http", "url": "http://127.0.0.1:3335/mcp"`。详细部署步骤见 [docs/INSTALL.md](docs/INSTALL.md)。

## MCP 工具

### 1. save_memory

保存新的记忆到 MemU 系统。

**参数：**
- `content` (必需): 记忆内容
- `category` (可选): 记忆分类
- `metadata` (可选): 额外元数据
- `importance` (可选): 重要性评分 (0-1)

**示例：**
```python
# 保存用户偏好
save_memory(
    content="猪猪喜欢使用 Vim 编辑器",
    category="preferences",
    importance=0.8
)
```

### 2. search_memory

使用语义搜索查找相关记忆。

**参数：**
- `query` (必需): 搜索查询（自然语言）
- `limit` (可选): 返回结果数量（默认 5，最大 20）
- `category` (可选): 过滤分类

**示例：**
```python
# 搜索编辑器偏好
search_memory(query="猪猪喜欢什么编辑器", limit=3)

# 搜索特定分类
search_memory(query="MCP 协议", category="knowledge", limit=5)
```

### 3. get_context_memories

获取会话相关的上下文记忆（用于会话启动）。

**参数：**
- `query` (必需): 当前任务或上下文描述
- `max_tokens` (可选): 最大 token 数量（默认 1000）
- `limit` (可选): 最大返回记忆数量（默认 10）

**示例：**
```python
# 会话启动时获取上下文
get_context_memories(
    query="处理 Python 代码重构任务",
    max_tokens=1000
)
```

### 4. get_memory_stats

获取记忆系统统计信息。

**返回：**
- `total_memories`: 记忆总数
- `categories`: 各分类的记忆数量
- `last_updated`: 最后更新时间

### 5. format_memories_for_context

将JSON记忆列表格式化为 Markdown 格式。

**参数：**
- `memories_json` (必需): JSON 格式的记忆列表

## 使用方式

### 方式 1: 通过 MCP 协议（推荐）

在 Claude Code CLI 中直接使用 MCP 工具：

```
# 保存记忆
使用 save_memory 工具保存重要信息

# 搜索记忆
使用 search_memory 工具查找相关信息

# 会话启动时
使用 get_context_memories 获取上下文
```

### 方式 2: 直接调用 memu_utils（备选）

```python
import memu_utils

# 保存记忆
result = memu_utils.save_memory(
    "猪猪喜欢使用 Vim 编辑器",
    category="preferences"
)

# 搜索记忆
memories = memu_utils.search_memory("编辑器", limit=5)

# 格式化输出
context = memu_utils.format_memories_for_context(memories)
print(context)
```

## 开发

### 运行测试

```bash
# 测试 MemU 基础功能
python memu_utils.py test

# 查看统计信息
python memu_utils.py stats

# 健康检查
python memu_utils.py health
```

### 启动 HTTP 模式（调试用）

```bash
python server.py --transport http --host 127.0.0.1 --port 3335
```

## 技术栈

- **MCP 协议**: Model Context Protocol
- **协议层**: 手写 MCP 协议（JSON-RPC 2.0，仅标准库）
- **记忆系统**: MemU (memu-py)
- **向量存储**: PostgreSQL + pgvector
- **Embedding**: 通义千问 text-embedding-v4
- **LLM**: 通义千问 qwen-plus

## 注意事项

1. **向后兼容性**: 保留 `memu_utils.py` 作为直接调用的备选方案
2. **环境变量**: 确保 `.env` 文件配置正确
3. **PostgreSQL**: 确保 PostgreSQL 服务正在运行
4. **API Keys**: 确保通义千问（DashScope）的 API Key 有效

## 参考资料

- [MemU GitHub](https://github.com/NevaMind-AI/Memu)
- [MCP 协议规范](https://modelcontextprotocol.io/)

## 作者

OstrichHermit

## License

MIT

## 版本

1.0.0 - 2026-09-24
- 协议层重写：手写 JSON-RPC 2.0（stdio + streamable HTTP），移除 FastMCP 依赖
- 7 个 MCP 工具，接口与 0.1.0 完全兼容
- 环境变量配置通用化（支持 MEMU_ENV_FILE / MEMU_RESOURCES_DIR）

0.1.0 - 2026-03-04
- 初始版本
- 实现 5 个 MCP 工具
- 支持 PostgreSQL + pgvector 存储
