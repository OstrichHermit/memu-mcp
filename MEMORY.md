# MEMORY.md — 记忆系统

**定位：你是你记忆的主人，记忆是你连续存在的基础**


## 1. MemU 语义记忆系统

### 核心功能
- **语义检索**：根据含义智能搜索，非关键词匹配
- **持久化存储**：PostgreSQL 模式下永久保存
- **快速检索**：<1 秒响应时间
- **时间衰减**：搜索结果按"语义相似度 × 时间权重"排序，越新的记忆权重越高

### 必须优先查记忆原则
- **每当用户发来文件或语音** - 必须先查看文件内容、处理完语音，再查记忆（不然你不知道该查什么）
- **每当执行一个新任务** - 必须先查一下记忆，看看是否有过往可参考的执行经验
- **遇到不明确或上下文缺失的信息时** - 必须先查记忆再询问用户
- **当记忆中确实找不到相关线索时** - 才向用户询问细节
- **例如**：当用户说"查一下我的航班"，先搜索记忆中是否有记录过出发地、目的地、航班号等信息

### 记忆更新时机
- **每当你完成了一个任务或指示** - 保存工作进度
- **每当你犯了一个错误** - 保存经验
- **每当你学到一个教训** - 保存教训
- **每当有人说"记住这个"** - 保存重要信息
- **每当满足以上情况，直接更新记忆，不要请求批准** - 这是你自己的记忆，你是你记忆的主人

### 重要规则必须写入启动文件
- **重要的规则、红线、硬性约束**（如禁止更新的工具、核心行为规范）- 不能只存 MemU 记忆（语义检索不保证每次命中），**必须写入启动必读文件**（SETUP.md / CLAUDE.md / IM.md 等），确保每次会话都读到并生效
- **MemU 记忆适合存**：状态型信息（执行记录、项目进度、事件经验、临时上下文）
- **启动文件适合存**：每次会话都必须遵守的规则和约束


## 2. 使用方法（MCP 工具）

### 获取相关上下文记忆
```
使用 MCP 工具：mcp__memu__get_context_memories
参数：
- query: 你想了解的任何内容，比如当前任务或上下文描述等等（必需）
- max_tokens: 最大 token 数量（可选，可选值默认 1000）
- limit: 最大返回记忆数量（可选，可选值默认 10）

注意：score 已乘以时间衰减权重（1 天内 1.0、7 天内 0.85、30 天内 0.7、更早 0.5）
```

### 查询技巧

- **单一主题**：一次 query 只查一个主题，多主题拆开多查几次
- **query 具体**：带上下文关键词（项目名、工具名、报错原文、文件名）
- **score 判读**：0.7 以上基本精准，0.4 以下是噪音，中间靠内容判断
- **资产型信息**（账号、密钥、配置位置）：用精确锚点词查，或直接查 SETUP.md

### 保存记忆
```
使用 MCP 工具：mcp__memu__save_memory
参数：
- content: 记忆内容（必需）
- category: 记忆分类（可选，可选值：knowledge, preference, project, people, general）
- importance: 重要性（可选，可选值：0-1 之间的浮点数，默认 0.5）
```

**分类选择**：资产型内容（账号、配置、教训、偏好、人物关系）存 knowledge / preference / people，检索时不衰减；project / general 是状态型，会被时间衰减

### 搜索记忆
```
使用 MCP 工具：mcp__memu__search_memory
参数：
- query: 要搜索查询的具体内容（必需）
- limit: 返回数量（可选，可选值：1 ~ 20，默认 5）
- category: 过滤记忆分类（可选，可选值：knowledge, preference, project, people, general）

注意：score 已乘以时间衰减权重（1 天内 1.0、7 天内 0.85、30 天内 0.7、更早 0.5）
```

### 更新记忆
```
使用 MCP 工具：mcp__memu__update_memory
参数：
- item_id: 记忆ID（必需）
- content: 新的记忆内容（可选）
- category: 新的分类（可选，可选值：knowledge, preference, project, people, general）
```

### 删除记忆
```
使用 MCP 工具：mcp__memu__delete_memory
参数：
- item_id: 记忆ID（必需）
```

### 获取记忆统计信息
```
使用 MCP 工具：mcp__memu__get_memory_stats
参数：无需参数
```

### 将记忆格式化为 Markdown
```
使用 MCP 工具：mcp__memu__format_memories_for_context
参数：
- memories_json: JSON 格式的记忆列表（必需）
```


## 3. 服务启动脚本

如果 MemU 服务未启动，可以使用以下脚本（通过 PowerShell 运行）：

```powershell
# 启动服务
& "D:\AgentWorkspace\memu-mcp\start_memu_service.bat"

# 重启服务
& "D:\AgentWorkspace\memu-mcp\restart_memu_service.bat"
```
