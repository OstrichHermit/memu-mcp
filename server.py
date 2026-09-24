#!/usr/bin/env python3
"""MemU MCP Server - memory system interface for Claude Code

为 Claude Code 提供 MemU 记忆系统的 MCP 接口。

手写 MCP 协议（JSON-RPC 2.0），协议层仅用标准库：
- stdio 模式：newline-delimited JSON-RPC（与 image-mcp 一致）
- http 模式：streamable HTTP（POST /mcp，JSON 响应），附带 OAuth 模拟端点

架构：
    Claude Code CLI
        ↓ (MCP 协议)
    server.py (协议层)
        ↓ (调用)
    memu_utils (辅助层)
        ↓ (存储)
    MemU (memu-py) + PostgreSQL + pgvector

依赖：memu-py、openai、python-dotenv（业务层），无第三方 MCP 框架依赖。
"""
import asyncio
import json
import logging
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# 添加当前目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

import memu_utils

# ==================== 日志（文件 + stderr，stdout 仅输出协议消息） ====================

SERVER_DIR = Path(__file__).parent.resolve()
LOG_DIR = SERVER_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "memu.log"

logger = logging.getLogger("memu")
logger.setLevel(logging.INFO)
logger.propagate = False
_fmt = logging.Formatter("[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
_fh = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
_fh.setFormatter(_fmt)
logger.addHandler(_fh)
_sh = logging.StreamHandler(sys.stderr)
_sh.setFormatter(_fmt)
logger.addHandler(_sh)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "memu", "version": "1.0.0"}

# 全局事件循环：所有工具调用都在同一个 loop 上执行，
# 保证 memu_utils 内部的 asyncio.Lock 与连接池跨调用安全。
LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(LOOP)


def log(*a):
    logger.info(" ".join(str(x) for x in a))


# ==================== 工具定义 ====================

SAVE_MEMORY_TOOL = {
    "name": "save_memory",
    "description": """保存记忆到 MemU

将新的记忆保存到 MemU 系统中,支持自动分类和元数据管理。
记忆将使用语义向量索引,便于后续检索。

Args:
    content: 记忆内容(必需),支持 Markdown 格式
    category: 记忆分类(可选),推荐值:
        - 'knowledge': 知识和经验(技术笔记、调试经验、教训)
        - 'preference': 偏好(用户习惯、工作方式)
        - 'project': 项目(项目信息、状态、进度)
        - 'people': 人物(关系信息、用户资料)
        - 'general': 其他(默认)
    metadata: 额外元数据(可选),JSON 格式
    importance: 重要性评分(可选),0-1 之间的浮点数

Returns:
    JSON格式的保存结果,包含成功状态和记忆ID

Note:
    - 记忆将自动进行语义向量化
    - 支持中文和英文语义检索
    - 数据持久化存储到 PostgreSQL
    - 保存后约 1-2 秒即可检索到新记忆""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "记忆内容(必需),支持 Markdown 格式"},
            "category": {
                "type": "string",
                "description": "记忆分类(可选): knowledge, preference, project, people, general",
            },
            "metadata": {
                "type": "object",
                "description": "额外元数据(可选),JSON 对象,如 {\"tags\": [\"重要\"]}",
            },
            "importance": {
                "type": "number",
                "description": "重要性评分(可选),0-1 浮点数,越高越优先检索",
            },
        },
        "required": ["content"],
    },
}

SEARCH_MEMORY_TOOL = {
    "name": "search_memory",
    "description": """搜索记忆(语义检索)

使用自然语言查询搜索相关记忆。使用语义向量检索,理解查询意图,
可以找到与查询意图相关的记忆,而不仅仅是关键词匹配。

Args:
    query: 搜索查询(必需),自然语言描述
    limit: 返回结果数量(可选),默认 5,最大 20
    category: 过滤分类(可选),只检索指定分类的记忆

Returns:
    JSON格式的搜索结果列表,每个结果包含:
    - content: 记忆内容
    - score: 相关性评分(0-1,已乘时间衰减权重: 1天内1.0/7天内0.85/30天内0.7/更早0.5;
      资产型分类 knowledge/preference/people 不衰减)
    - category: 记忆分类
    - created_at: 创建时间

Note:
    - 相关性评分 >0.7 的结果通常比较准确
    - 如果找不到相关记忆,返回空列表
    - 搜索响应时间通常 < 1 秒""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询(必需),自然语言描述"},
            "limit": {"type": "integer", "description": "返回结果数量(可选),默认 5,最大 20", "default": 5},
            "category": {
                "type": "string",
                "description": "过滤分类(可选): knowledge, preference, project, people, general",
            },
        },
        "required": ["query"],
    },
}

GET_CONTEXT_MEMORIES_TOOL = {
    "name": "get_context_memories",
    "description": """获取上下文记忆(用于会话启动)

根据当前任务或上下文,智能检索相关记忆。
返回的记忆会控制在指定的 token 限制内,适合用于构建对话上下文。

Args:
    query: 当前任务或上下文描述(必需)
    max_tokens: 最大 token 数量限制(可选),默认 1000
        - 较小的值(500): 只获取最核心的记忆
        - 中等值(1000): 平衡的记忆集合(推荐)
        - 较大的值(2000-3000): 更全面的上下文
    limit: 最大返回记忆数量(可选),默认 10

Returns:
    JSON格式的相关记忆列表,按相关性排序

Note:
    - 这是会话启动时使用的工具
    - 自动控制 token 数量,避免超出限制
    - 建议在每次会话开始时调用一次""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "当前任务或上下文描述(必需)"},
            "max_tokens": {
                "type": "integer",
                "description": "最大 token 数量(可选),默认 1000",
                "default": 1000,
            },
            "limit": {
                "type": "integer",
                "description": "最大返回记忆数量(可选),默认 10",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}

GET_MEMORY_STATS_TOOL = {
    "name": "get_memory_stats",
    "description": """获取记忆系统统计信息

返回 MemU 系统的统计数据,包括记忆总数、分类分布等信息。

Returns:
    JSON格式的统计信息,包含:
    - total_memories: 记忆总数
    - categories: 各分类的记忆数量
    - last_updated: 最后更新时间""",
    "inputSchema": {"type": "object", "properties": {}},
}

UPDATE_MEMORY_TOOL = {
    "name": "update_memory",
    "description": """更新已有记忆

更新指定记忆的内容和/或分类。更新内容时会自动重新计算语义向量。

Args:
    item_id: 记忆ID(必需),通过 search_memory 获取
    content: 新的记忆内容(可选),不传则保持原内容
    category: 新的分类(可选),不传则保持原分类

Note:
    - content 和 category 至少提供一个
    - 更新内容时会自动重新计算 embedding 向量
    - 如果记忆ID不存在,会返回错误""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "记忆ID(必需)"},
            "content": {"type": "string", "description": "新的记忆内容(可选)"},
            "category": {
                "type": "string",
                "description": "新的分类(可选): knowledge, preference, project, people, general",
            },
        },
        "required": ["item_id"],
    },
}

DELETE_MEMORY_TOOL = {
    "name": "delete_memory",
    "description": """删除记忆

永久删除指定的记忆,此操作不可逆。

Args:
    item_id: 记忆ID(必需),通过 search_memory 获取

Note:
    - 此操作不可逆,请谨慎使用
    - 如果记忆ID不存在,会返回错误""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "记忆ID(必需)"}
        },
        "required": ["item_id"],
    },
}

FORMAT_MEMORIES_TOOL = {
    "name": "format_memories_for_context",
    "description": """将记忆列表格式化为 Markdown 上下文

将 JSON 格式的记忆列表转换为易读的 Markdown 格式,
适合直接用于对话上下文或文档生成。

Args:
    memories_json: JSON 格式的记忆列表(必需)
        通常来自 search_memory 或 get_context_memories 的返回值""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "memories_json": {
                "type": "string",
                "description": "JSON 格式的记忆列表(必需)",
            }
        },
        "required": ["memories_json"],
    },
}

TOOLS = [
    SAVE_MEMORY_TOOL,
    SEARCH_MEMORY_TOOL,
    GET_CONTEXT_MEMORIES_TOOL,
    GET_MEMORY_STATS_TOOL,
    UPDATE_MEMORY_TOOL,
    DELETE_MEMORY_TOOL,
    FORMAT_MEMORIES_TOOL,
]


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _text_content(text: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


async def run_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """分发工具调用,返回 MCP content 结果。"""
    if name == "save_memory":
        result = await memu_utils.asave_memory(
            content=args.get("content", ""),
            category=args.get("category"),
            metadata=args.get("metadata"),
            importance=args.get("importance"),
        )
        return _text_content(_dump(result))

    if name == "search_memory":
        results = await memu_utils.asearch_memory(
            query=args.get("query", ""),
            limit=min(int(args.get("limit", 5) or 5), 20),
            category=args.get("category"),
        )
        return _text_content(_dump(results))

    if name == "get_context_memories":
        results = await memu_utils.aget_context_memories(
            query=args.get("query", ""),
            max_tokens=int(args.get("max_tokens", 1000) or 1000),
            limit=int(args.get("limit", 10) or 10),
        )
        return _text_content(_dump(results))

    if name == "get_memory_stats":
        try:
            stats = await asyncio.wait_for(memu_utils.aget_memory_stats(), timeout=30.0)
        except asyncio.TimeoutError:
            return _text_content(_dump({"error": "操作超时", "suggestion": "请检查数据库连接和网络"}))
        if stats:
            return _text_content(_dump(stats))
        return _text_content(_dump({"error": "无法获取统计信息", "suggestion": "请检查 MemU 服务是否正常运行"}))

    if name == "update_memory":
        result = await memu_utils.aupdate_memory(
            item_id=args.get("item_id", ""),
            content=args.get("content"),
            category=args.get("category"),
        )
        return _text_content(_dump(result))

    if name == "delete_memory":
        result = await memu_utils.adelete_memory(item_id=args.get("item_id", ""))
        return _text_content(_dump(result))

    if name == "format_memories_for_context":
        try:
            memories = json.loads(args.get("memories_json", "[]"))
        except json.JSONDecodeError:
            return _text_content("错误：无法解析 JSON 格式的记忆列表")
        return _text_content(memu_utils.format_memories_for_context(memories))

    raise ValueError(f"未知工具: {name}")


# ==================== JSON-RPC 消息处理 ====================

async def handle_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """处理一条 JSON-RPC 请求/通知。通知返回 None,请求返回响应。"""
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    def reply(result):
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    def reply_error(code, message):
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if isinstance(requested, str) else PROTOCOL_VERSION
        return reply({
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "tools/list":
        return reply({"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        t0 = datetime.now()
        try:
            result = await run_tool(name, args)
            log(f"工具 {name} 完成 ({(datetime.now() - t0).total_seconds():.2f}s)")
            return reply(result)
        except Exception as ex:
            log(f"工具 {name} 执行失败: {ex}")
            return reply({
                "content": [{"type": "text", "text": f"工具执行失败: {ex}"}],
                "isError": True,
            })

    if method == "ping":
        return reply({})

    if msg_id is not None:
        return reply_error(-32601, f"方法不存在: {method}")
    return None


# ==================== stdio 传输 ====================

def serve_stdio():
    """newline-delimited JSON-RPC over stdio。

    所有工具调用都提交到全局 LOOP(run_until_complete 复用同一循环),
    与 memu_utils 内部的事件循环假设兼容。
    """
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    def write(obj: Dict[str, Any]):
        sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    log(f"{SERVER_INFO['name']} v{SERVER_INFO['version']} 已启动（stdio，等待客户端）")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as ex:
            write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"JSON 解析失败: {ex}"}})
            continue
        try:
            resp = LOOP.run_until_complete(handle_message(msg))
        except Exception as ex:
            log(f"消息处理异常: {ex}")
            resp = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": f"内部错误: {ex}"}}
        if resp is not None:
            write(resp)


# ==================== HTTP 传输（streamable HTTP + OAuth 模拟端点） ====================

_sessions: Dict[str, bool] = {}
_oauth_codes: Dict[str, Dict[str, str]] = {}


def serve_http(host: str, port: int):
    """MCP over streamable HTTP（JSON 响应模式）。

    主线程运行全局事件循环,HTTP handler 线程通过
    run_coroutine_threadsafe 提交工具调用。
    """
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlparse, parse_qs

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # 静默默认访问日志
            pass

        # ---------- 基础工具 ----------

        def _send_json(self, obj, status: int = 200, extra_headers: Optional[Dict[str, str]] = None):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra_headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, location: str):
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _read_body(self) -> bytes:
            length = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(length) if length else b""

        def _call_mcp(self, msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            fut = asyncio.run_coroutine_threadsafe(handle_message(msg), LOOP)
            return fut.result(timeout=300)

        # ---------- MCP 端点 ----------

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/mcp":
                try:
                    msg = json.loads(self._read_body().decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as ex:
                    self._send_json({"jsonrpc": "2.0", "id": None,
                                     "error": {"code": -32700, "message": f"JSON 解析失败: {ex}"}}, 400)
                    return

                messages = msg if isinstance(msg, list) else [msg]
                responses = []
                for m in messages:
                    resp = self._call_mcp(m)
                    if resp is not None:
                        responses.append(resp)

                headers: Dict[str, str] = {}
                if isinstance(msg, dict) and msg.get("method") == "initialize":
                    sid = uuid.uuid4().hex
                    _sessions[sid] = True
                    headers["Mcp-Session-Id"] = sid
                elif self.headers.get("Mcp-Session-Id"):
                    headers["Mcp-Session-Id"] = self.headers["Mcp-Session-Id"]

                if not responses:
                    self.send_response(202)
                    self.send_header("Content-Length", "0")
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.end_headers()
                else:
                    payload = responses[0] if len(responses) == 1 else responses
                    self._send_json(payload, 200, headers)
                return

            if path == "/oauth/token":
                body = self._read_body().decode("utf-8", errors="replace")
                fields = dict(pair.split("=", 1) for pair in body.split("&") if "=" in pair)
                code = fields.get("code", "")
                if code and code in _oauth_codes:
                    del _oauth_codes[code]
                self._send_json({
                    "access_token": f"dummy-{uuid.uuid4().hex[:32]}",
                    "token_type": "Bearer",
                    "expires_in": 86400,
                    "scope": fields.get("scope", "mcp"),
                })
                return

            if path == "/oauth/register":
                try:
                    body = json.loads(self._read_body().decode("utf-8") or "{}")
                except json.JSONDecodeError:
                    body = {}
                self._send_json({
                    "client_id": f"mcp-{uuid.uuid4().hex[:8]}",
                    "client_secret": f"secret-{uuid.uuid4().hex[:16]}",
                    "client_name": body.get("client_name", "MCP Client"),
                    "redirect_uris": body.get("redirect_uris", []),
                    "grant_types": ["authorization_code"],
                    "response_types": ["code"],
                    "token_endpoint_auth_method": "client_secret_post",
                })
                return

            self._send_json({"error": "not found"}, 404)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/mcp":
                # 无状态服务器：不支持 GET 建立服务器→客户端 SSE 流
                self.send_response(405)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            base_url = f"http://{host}:{port}"
            if path == "/.well-known/oauth-protected-resource":
                self._send_json({
                    "authorization_servers": [base_url],
                    "resource": f"{base_url}/mcp",
                })
                return
            if path == "/.well-known/oauth-authorization-server":
                self._send_json({
                    "issuer": base_url,
                    "authorization_endpoint": f"{base_url}/oauth/authorize",
                    "token_endpoint": f"{base_url}/oauth/token",
                    "registration_endpoint": f"{base_url}/oauth/register",
                    "response_types_supported": ["code"],
                    "grant_types_supported": ["authorization_code"],
                    "code_challenge_methods_supported": ["S256"],
                    "token_endpoint_auth_methods_supported": ["client_secret_post"],
                    "scopes_supported": ["mcp"],
                })
                return
            if path == "/oauth/authorize":
                qs = parse_qs(urlparse(self.path).query)
                redirect_uri = qs.get("redirect_uri", [""])[0]
                state = qs.get("state", [""])[0]
                code = uuid.uuid4().hex[:16]
                _oauth_codes[code] = {
                    "redirect_uri": redirect_uri,
                    "client_id": qs.get("client_id", [""])[0],
                    "code_challenge": qs.get("code_challenge", [""])[0],
                }
                sep = "&" if "?" in redirect_uri else "?"
                self._redirect(f"{redirect_uri}{sep}code={code}&state={state}")
                return

            self._send_json({"error": "not found"}, 404)

        def do_DELETE(self):
            if urlparse(self.path).path == "/mcp":
                sid = self.headers.get("Mcp-Session-Id")
                if sid:
                    _sessions.pop(sid, None)
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._send_json({"error": "not found"}, 404)

    server = ThreadingHTTPServer((host, port), Handler)
    log(f"{SERVER_INFO['name']} v{SERVER_INFO['version']} 已启动（HTTP，监听 {host}:{port}/mcp）")
    http_thread = threading.Thread(target=server.serve_forever, daemon=True)
    http_thread.start()
    try:
        LOOP.run_forever()
    except KeyboardInterrupt:
        log("收到中断信号，服务器正在关闭...")
    finally:
        server.shutdown()


# ==================== 启动入口 ====================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="MemU MCP Server - 个人知识记忆系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  # stdio 模式（推荐，用于 Claude Code）
  python server.py

  # HTTP 模式（可被 mcp-manager 等工具统一管理）
  python server.py --transport http --host 127.0.0.1 --port 3335

  # 检查 MemU 是否可用
  python memu_utils.py health
""",
    )
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio",
                        help="传输模式：stdio (默认) 或 http")
    parser.add_argument("--host", default="127.0.0.1", help="HTTP 模式的监听地址")
    parser.add_argument("--port", type=int, default=3335, help="HTTP 模式的监听端口，默认 3335")
    parser.add_argument("--project", default=None, help="项目标识，用于进程管理")
    parser.add_argument("--name", default=None, help="服务名称，用于进程管理")
    args = parser.parse_args()

    log("=" * 60)
    log("  MemU MCP Server - 记忆系统")
    log("=" * 60)
    log(f"  传输模式: {args.transport.upper()}")
    log(f"  日志文件: {LOG_FILE}")
    if args.transport == "http":
        log(f"  服务器监听: {args.host}:{args.port}/mcp")
    log("  已注册的工具: " + ", ".join(t["name"] for t in TOOLS))
    log("=" * 60)

    try:
        if args.transport == "stdio":
            serve_stdio()
        elif args.transport == "http":
            serve_http(args.host, args.port)
        else:
            raise ValueError(f"不支持的传输模式: {args.transport}")
    except Exception as e:
        logger.error(f"[ERROR] 服务器崩溃: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
