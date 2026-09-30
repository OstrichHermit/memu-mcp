"""
MemU 记忆系统辅助工具

为 Agent 工作空间提供记忆管理功能，
与 MemU 系统深度集成，支持语义检索和智能上下文获取。

作者：OstrichHermit
"""

import asyncio
import os
import threading
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional, Any
from datetime import datetime
import json
import logging

import dashscope
from http import HTTPStatus

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 加载环境变量（从多个可能的位置）：
# 1. 项目自身目录的 .env（独立布局：memu-mcp/.env 与代码同目录）
# 2. MEMU_ENV_FILE 环境变量指定的位置
load_dotenv()
load_dotenv(str(Path(__file__).resolve().parent / ".env"))
if os.getenv("MEMU_ENV_FILE"):
    load_dotenv(os.getenv("MEMU_ENV_FILE"))

# ==================== 配置 ====================

# 可配置项（均可在项目 .env 中覆盖，见文件内注释）
CHAT_MODEL = os.getenv("MEMU_CHAT_MODEL", "qwen-plus")
CHAT_BASE_URL = os.getenv("MEMU_CHAT_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
EMBED_MODEL = os.getenv("MEMU_EMBED_MODEL", "qwen3.7-text-embedding")
# embedding 后端：dashscope=原生 SDK（支持 text_type/instruct）| openai=兼容接口（基础稠密向量）
EMBED_BACKEND = os.getenv("MEMU_EMBED_BACKEND", "dashscope").strip().lower()
EMBED_BASE_URL = os.getenv("MEMU_EMBED_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
# dashscope 模式接口地址：MEMU_DASHSCOPE_BASE_URL > DASHSCOPE_BASE_URL > 官方主域名
DASHSCOPE_API_URL = (
    os.getenv("MEMU_DASHSCOPE_BASE_URL")
    or os.getenv("DASHSCOPE_BASE_URL")
    or "https://dashscope.aliyuncs.com/api/v1"
)
# 查询侧检索指令（仅 dashscope 模式 + text_type=query 时生效）
SEARCH_INSTRUCT = os.getenv(
    "MEMU_SEARCH_INSTRUCT",
    "Given a personal memory search query, retrieve the most relevant memory records"
)

# LLM 配置
LLM_PROFILES = {
    "default": {
        "base_url": CHAT_BASE_URL,
        "api_key": os.getenv("DASHSCOPE_API_KEY"),
        "chat_model": CHAT_MODEL,
        "client_backend": "sdk",
    },
    "embedding": {
        "base_url": EMBED_BASE_URL,
        "api_key": os.getenv("DASHSCOPE_API_KEY"),
        "embed_model": EMBED_MODEL,
    }
}

# ==================== DashScope 原生向量化 ====================

dashscope.base_http_api_url = DASHSCOPE_API_URL

# 同步接口单次最大行数（官方 SDK 示例值）
_EMBED_BATCH_SIZE = 10


def embed_texts(
    texts: List[str],
    text_type: str = "document",
    instruct: Optional[str] = None
) -> List[List[float]]:
    """批量向量化，返回与输入顺序一致的向量列表

    后端由 MEMU_EMBED_BACKEND 决定：
    - dashscope：原生 SDK，支持 text_type（document/query）与 instruct
    - openai：兼容接口，仅基础稠密向量（高级参数不传）
    """
    if EMBED_BACKEND == "openai":
        return _embed_openai(texts)
    return _embed_dashscope(texts, text_type, instruct)


def _embed_openai(texts: List[str]) -> List[List[float]]:
    from openai import OpenAI
    client = OpenAI(
        base_url=EMBED_BASE_URL,
        api_key=LLM_PROFILES["embedding"]["api_key"]
    )
    result: List[List[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[start:start + _EMBED_BATCH_SIZE]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        data = sorted(resp.data, key=lambda d: d.index)
        result.extend(d.embedding for d in data)
    return result


def _embed_dashscope(
    texts: List[str],
    text_type: str,
    instruct: Optional[str]
) -> List[List[float]]:
    dashscope.api_key = LLM_PROFILES["embedding"]["api_key"]
    result: List[Optional[List[float]]] = [None] * len(texts)
    for start in range(0, len(texts), _EMBED_BATCH_SIZE):
        batch = texts[start:start + _EMBED_BATCH_SIZE]
        kwargs: Dict[str, Any] = {
            "model": EMBED_MODEL,
            "input": batch,
            "text_type": text_type,
        }
        if text_type == "query" and instruct:
            kwargs["instruct"] = instruct
        resp = dashscope.TextEmbedding.call(**kwargs)
        if resp.status_code != HTTPStatus.OK:
            raise RuntimeError(
                f"DashScope 向量化失败: status={resp.status_code} code={getattr(resp, 'code', '')} msg={getattr(resp, 'message', '')}"
            )
        for emb in resp.output["embeddings"]:
            result[start + emb["text_index"]] = emb["embedding"]
    return result

# ==================== 服务初始化 ====================

_service_instance = None
_service_lock = asyncio.Lock()
# 全局事件循环（用于同步调用）
_event_loop = None
_loop_lock = threading.Lock()


def _get_or_create_event_loop():
    """获取或创建全局事件循环"""
    global _event_loop
    with _loop_lock:
        if _event_loop is None or _event_loop.is_closed():
            _event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_event_loop)
        return _event_loop


def get_service():
    """获取 MemU 服务实例（同步）"""
    global _service_instance
    if _service_instance is not None:
        return _service_instance

    try:
        from memu.app.service import MemoryService

        database_type = os.getenv("DATABASE_TYPE", "postgres")
        postgres_dsn = os.getenv("POSTGRES_DSN", "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/memu")

        blob_config = {
            "provider": "local",
            "resources_dir": os.getenv(
                "MEMU_RESOURCES_DIR",
                str(Path(__file__).resolve().parent / "data" / "resources")
            )
        }

        database_config = {
            "metadata_store": {
                "provider": "postgres",
                "dsn": postgres_dsn,
                "ddl_mode": "validate",
            },
        }

        logger.info(f"初始化 MemU 服务 (database_type={database_type})")
        _service_instance = MemoryService(
            llm_profiles=LLM_PROFILES,
            blob_config=blob_config,
            database_config=database_config,
            retrieve_config={"method": "rag"}
        )
        logger.info("MemU 服务初始化成功")
        return _service_instance

    except Exception as e:
        logger.error(f"初始化 MemU 服务失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def async_get_service():
    """异步获取服务实例"""
    global _service_instance
    if _service_instance is not None:
        return _service_instance

    async with _service_lock:
        if _service_instance is not None:
            return _service_instance

        loop = asyncio.get_event_loop()
        service = await loop.run_in_executor(None, get_service)

        if service is None:
            raise RuntimeError("无法初始化 MemU 服务")

        return service


# ==================== 核心功能（异步版本） ====================

async def asave_memory(
    content: str,
    category: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    importance: Optional[float] = None
) -> Dict[str, Any]:
    """保存记忆（异步版本）

    直接对内容做 embedding 并存入数据库，跳过 LLM 二次摘要，
    因为调用方（AI）已经总结好了内容，无需再压缩。
    """
    try:
        service = await async_get_service()
        if not service:
            return {"status": "error", "error": "无法初始化 MemU 服务"}

        # 直接用 embedding 模型对原始内容向量化（入库侧用 document 角色）
        embedding = embed_texts([content], text_type="document")[0]

        # 确定记忆类型
        valid_types = {"knowledge", "preference", "project", "people", "general"}
        memory_type = category if category in valid_types else "knowledge"

        # 先创建 resource 记录（外键约束要求）
        resource = service.database.resource_repo.create_resource(
            url="memory://direct_save",
            modality="text",
            local_path="",
            caption=content[:200],
            embedding=embedding,
            user_data={},
        )

        # 再创建 memory item，使用 resource 自动生成的 ID
        memory_item = service.database.memory_item_repo.create_item(
            resource_id=resource.id,
            memory_type=memory_type,
            summary=content,
            embedding=embedding,
            user_data={},
        )

        logger.info(f"成功保存记忆（直接 embedding）: {content[:50]}...")
        return {
            "status": "success",
            "message": "记忆已保存",
            "id": str(memory_item.id),
            "created_at": str(memory_item.created_at),
            "category": memory_item.memory_type,
            "content": content[:100] + "..." if len(content) > 100 else content
        }

    except Exception as e:
        logger.error(f"保存记忆失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "message": "保存记忆失败"
        }


# 资产型记忆：事实/偏好/人物关系不会随时间过时，不参与时间衰减
ASSET_CATEGORIES = {"knowledge", "preference", "people"}


def _time_decay_weight(created_at, category: Optional[str] = None) -> float:
    """计算时间衰减权重（按 category 差异化）

    资产型（knowledge/preference/people）: 恒为 1.0，不衰减
    状态型（project/general/未分类）: 1天内 1.0, 7天内 0.85, 30天内 0.7, 更早 0.5
    """
    if category in ASSET_CATEGORIES:
        return 1.0
    from datetime import datetime, timezone
    if not created_at:
        return 0.5
    try:
        if isinstance(created_at, str):
            # 处理各种时间字符串格式
            created_at = created_at.replace("+08:00", "+00:00").replace("+00:00", "")
            created_at = datetime.fromisoformat(created_at)
        if created_at.tzinfo:
            now = datetime.now(created_at.tzinfo)
        else:
            now = datetime.now(timezone.utc)
        delta_hours = (now - created_at).total_seconds() / 3600
        if delta_hours <= 24:
            return 1.0
        elif delta_hours <= 168:  # 7天
            return 0.85
        elif delta_hours <= 720:  # 30天
            return 0.7
        else:
            return 0.5
    except Exception:
        return 0.5


async def asearch_memory(
    query: str,
    limit: int = 5,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """搜索记忆（异步版本）"""
    try:
        service = await async_get_service()
        if not service:
            return []

        query_embedding = embed_texts(
            [query],
            text_type="query",
            instruct=SEARCH_INSTRUCT
        )[0]

        repo = service.database.memory_item_repo
        # 衰减重排发生在检索之后，向量分排名不等于衰减后排名，
        # 预筛池太小会误杀"低向量分但高衰减后分"的记忆，所以统一扩到 100
        search_limit = max(limit * 3, 100)
        # v1.5.1 起过滤参数从 memory_type 改为通用 where dict
        search_results = repo.vector_search_items(
            query_vec=query_embedding,
            top_k=search_limit,
            where={"memory_type": category} if category else None
        )

        items = []
        for item_id, score in search_results:
            item = repo.get_item(item_id)
            if item:
                # 应用时间衰减权重（按 category 差异化）
                decay = _time_decay_weight(
                    item.created_at,
                    item.memory_type if hasattr(item, 'memory_type') else None
                )
                adjusted_score = score * decay
                item_dict = {
                    "id": str(item.id) if hasattr(item, 'id') else item_id,
                    "content": item.summary if hasattr(item, 'summary') else "",
                    "score": round(adjusted_score, 4),
                    "category": item.memory_type if hasattr(item, 'memory_type') else "未分类",
                    "created_at": str(item.created_at) if hasattr(item, 'created_at') else ""
                }
                items.append(item_dict)

        # 按调整后的评分重新排序并截取
        items.sort(key=lambda x: x["score"], reverse=True)
        return items[:limit]

    except Exception as e:
        logger.error(f"搜索记忆失败: {e}")
        import traceback
        traceback.print_exc()
        return []


async def aget_context_memories(
    query: str,
    max_tokens: int = 1000,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """获取上下文记忆（异步版本）"""
    try:
        candidates = await asearch_memory(query, limit=limit * 2)

        selected = []
        current_tokens = 0

        for memory in candidates:
            if len(selected) >= limit:
                break
            content = memory.get("content", "")
            content_tokens = len(content) // 3

            if current_tokens + content_tokens <= max_tokens:
                selected.append(memory)
                current_tokens += content_tokens

        return selected

    except Exception as e:
        logger.error(f"获取上下文记忆失败: {e}")
        return []


async def aupdate_memory(
    item_id: str,
    content: Optional[str] = None,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """更新记忆（异步版本）"""
    try:
        service = await async_get_service()
        if not service:
            return {"status": "error", "error": "无法初始化 MemU 服务"}

        repo = service.database.memory_item_repo

        # 如果要更新内容，需要重新计算 embedding
        new_embedding = None
        if content is not None:
            new_embedding = embed_texts([content], text_type="document")[0]

        update_kwargs = {}
        if new_embedding is not None:
            update_kwargs["summary"] = content
            update_kwargs["embedding"] = new_embedding
        if category is not None:
            valid_types = {"knowledge", "preference", "project", "people", "general"}
            update_kwargs["memory_type"] = category if category in valid_types else None

        if not update_kwargs:
            return {"status": "error", "error": "没有提供要更新的字段"}

        updated = repo.update_item(item_id=item_id, **update_kwargs)

        logger.info(f"成功更新记忆: {item_id}")
        return {
            "status": "success",
            "message": "记忆已更新",
            "id": str(updated.id),
            "updated_at": str(updated.updated_at),
            "category": updated.memory_type,
        }

    except KeyError:
        return {"status": "error", "error": f"记忆 {item_id} 不存在"}
    except Exception as e:
        logger.error(f"更新记忆失败: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


async def adelete_memory(item_id: str) -> Dict[str, Any]:
    """删除记忆（异步版本）"""
    try:
        service = await async_get_service()
        if not service:
            return {"status": "error", "error": "无法初始化 MemU 服务"}

        repo = service.database.memory_item_repo

        # 先检查记忆是否存在
        item = repo.get_item(item_id)
        if item is None:
            return {"status": "error", "error": f"记忆 {item_id} 不存在"}

        repo.delete_item(item_id=item_id)

        logger.info(f"成功删除记忆: {item_id}")
        return {
            "status": "success",
            "message": "记忆已删除",
            "id": item_id
        }

    except Exception as e:
        logger.error(f"删除记忆失败: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


async def aget_memory_stats() -> Optional[Dict[str, Any]]:
    """获取统计信息（异步版本）"""
    try:
        service = await async_get_service()
        if not service:
            return None

        items = await service.list_memory_items()

        if isinstance(items, dict):
            items = items.get("items", [])

        categories = {}
        for item in items:
            if isinstance(item, dict):
                # ✅ 修复：使用 "memory_type" 而不是 "category"
                cat = item.get("memory_type", "未分类")
            elif hasattr(item, 'memory_type'):
                # ✅ 同时支持对象访问
                cat = item.memory_type
            else:
                cat = "未分类"
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_memories": len(items),
            "categories": categories,
            "last_updated": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"获取统计信息失败: {e}")
        return None


# ==================== 核心功能（同步版本） ====================

def _run_async(coro):
    """运行异步函数（使用全局事件循环）"""
    loop = _get_or_create_event_loop()
    return loop.run_until_complete(coro)


def save_memory(
    content: str,
    category: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    importance: Optional[float] = None
) -> Dict[str, Any]:
    """保存记忆（同步版本）"""
    return _run_async(asave_memory(content, category, metadata, importance))


def search_memory(
    query: str,
    limit: int = 5,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """搜索记忆（同步版本）"""
    return _run_async(asearch_memory(query, limit, category))


def get_context_memories(
    query: str,
    max_tokens: int = 1000,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """获取相关上下文记忆（同步版本）"""
    return _run_async(aget_context_memories(query, max_tokens, limit))


def get_memory_stats() -> Optional[Dict[str, Any]]:
    """获取记忆系统统计信息（同步版本）"""
    return _run_async(aget_memory_stats())


def format_memories_for_context(memories: List[Dict[str, Any]]) -> str:
    """将记忆列表格式化为上下文字符串"""
    if not memories:
        return "## 相关记忆\n\n暂无相关记忆。\n"

    lines = ["## 相关记忆\n"]
    lines.append(f"通过语义检索找到 {len(memories)} 条相关记忆\n\n")

    for i, memory in enumerate(memories, 1):
        content = memory.get("content", "")
        score = memory.get("score", 0)
        category = memory.get("category", "未分类")
        created_at = memory.get("created_at", "")

        relevance = min(score * 100, 99.9) if score else 0

        lines.append(f"### {i}. {category} (相关性: {relevance:.1f}%)\n")
        lines.append(f"{content}\n")

        if created_at:
            lines.append(f"*记录时间: {created_at}*\n")

        lines.append("\n")

    return "".join(lines)


def update_memory(
    item_id: str,
    content: Optional[str] = None,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """更新记忆（同步版本）"""
    return _run_async(aupdate_memory(item_id, content, category))


def delete_memory(item_id: str) -> Dict[str, Any]:
    """删除记忆（同步版本）"""
    return _run_async(adelete_memory(item_id))


# ==================== 实用工具 ====================

def check_memu_health() -> bool:
    """检查 MemU 是否可用"""
    try:
        from memu.app.service import MemoryService
        service = MemoryService(llm_profiles=LLM_PROFILES)
        return True
    except Exception as e:
        logger.warning(f"MemU 健康检查失败: {e}")
        return False


# ==================== 命令行接口 ====================

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "health":
        if check_memu_health():
            print("✅ MemU 可用")
            sys.exit(0)
        else:
            print("❌ MemU 不可用")
            sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        print("测试 MemU 功能...")

        print("\n[1/3] 保存测试记忆...")
        result = save_memory(
            "这是一条测试记忆 - MemU 集成测试",
            category="test"
        )
        print(f"保存结果: {result}")

        print("\n[2/3] 搜索测试...")
        results = search_memory("测试记忆", limit=3)
        print(f"搜索结果: {len(results)} 条")
        for mem in results:
            print(f"- {mem.get('content', '')[:50]}")

        print("\n[3/3] 格式化输出...")
        context = format_memories_for_context(results)
        print(context)

    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        stats = get_memory_stats()
        if stats:
            print("📊 MemU 记忆统计:")
            print(json.dumps(stats, indent=2, ensure_ascii=False))
        else:
            print("❌ 无法获取统计信息")

    if len(sys.argv) == 1:
        print(__doc__)
        print("\n命令行用法:")
        print("  python memu_utils.py health   - 检查可用性")
        print("  python memu_utils.py test     - 运行测试")
        print("  python memu_utils.py stats    - 查看统计")
