# MemU MCP Server - 快速参考

## MCP 工具快速参考

### 📝 保存记忆

```python
save_memory(
    content="要记住的内容",
    category="general",  # 可选: preferences, knowledge, projects, tasks
    importance=0.8      # 可选: 0-1 之间
)
```

### 🔍 搜索记忆

```python
search_memory(
    query="搜索查询（自然语言）",
    limit=5             # 可选: 返回数量，最大 20
)
```

### 📚 获取上下文记忆

```python
get_context_memories(
    query="当前任务描述",
    max_tokens=1000,    # 可选: token 限制
    limit=10            # 可选: 最大数量
)
```

### 📊 获取统计信息

```python
get_memory_stats()
```

### 🎨 格式化记忆

```python
format_memories_for_context(
    memories_json  # 来自 search_memory 的结果
)
```

## 推荐分类

- `preferences` - 用户偏好设置
- `knowledge` - 知识笔记
- `projects` - 项目信息
- `tasks` - 任务记录
- `relationships` - 人际关系
- `general` - 通用记忆（默认）

## 典型使用场景

### 1. 会话启动时

```python
# 获取上下文记忆
memories = await get_context_memories("处理代码重构任务")
```

### 2. 学习新知识时

```python
# 保存知识
await save_memory(
    content="MCP 协议基于 JSON-RPC 2.0",
    category="knowledge",
    importance=0.9
)
```

### 3. 需要查找信息时

```python
# 搜索相关记忆
results = await search_memory("MCP 协议", limit=5)
```

### 4. 记录用户偏好时

```python
# 保存偏好
await save_memory(
    content="猪猪喜欢使用 Vim 编辑器",
    category="preferences",
    importance=0.8
)
```

## 命令行工具

```bash
# 健康检查
python D:\AgentWorkspace\MemU\memu-mcp\memu_utils.py health

# 运行测试
python D:\AgentWorkspace\MemU\memu-mcp\memu_utils.py test

# 查看统计
python D:\AgentWorkspace\MemU\memu-mcp\memu_utils.py stats

# MCP 测试
cd D:\AgentWorkspace\MemU\memu-mcp
python test_mcp.py
```

## 配置文件位置

- **MCP 配置**: `D:\AgentWorkspace\.mcp.json`
- **环境变量**: `D:\AgentWorkspace\MemU\.env`
- **MCP Server**: `D:\AgentWorkspace\MemU\memu-mcp\`
- **工具函数**: `D:\AgentWorkspace\MemU\memu-mcp\memu_utils.py`

## 重要提示

⚠️ **每次保存记忆后，等待 1-2 秒再搜索**
⚠️ **搜索是语义的，不需要精确关键词**
⚠️ **重要性评分会影响检索优先级**
✅ **支持中英文混合查询**
✅ **数据持久化存储到 PostgreSQL**

---

版本: 0.1.0 | 更新: 2026-03-04
