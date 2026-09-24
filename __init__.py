"""
MemU MCP Server

为 Claude Code 提供 MemU 记忆系统的 MCP 接口。
支持保存记忆、语义搜索和上下文检索。

手写 MCP 协议（JSON-RPC 2.0），支持 stdio 与 streamable HTTP 两种传输。

作者：OstrichHermit
"""

__version__ = "1.0.0"
