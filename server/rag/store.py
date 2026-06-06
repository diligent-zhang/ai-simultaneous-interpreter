"""ChromaDB 向量存储 — 初始化 + CRUD。"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

COLLECTION_NAME = "glossary"
DATA_DIR = Path("server/data/chroma")


async def create_retriever():
    """创建检索器实例。加载 ChromaDB + 初始化默认术语表。"""
    from .retriever import Retriever
    from .glossary import DEFAULT_GLOSSARY

    try:
        import chromadb
    except ImportError:
        logger.warning("chromadb not installed, RAG disabled")
        return None

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(DATA_DIR))
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    if collection.count() == 0:
        logger.info("Seeding default glossary (%d terms)...", len(DEFAULT_GLOSSARY))
        await _seed_glossary(collection, DEFAULT_GLOSSARY)
        logger.info("Default glossary seeded")

    return Retriever(collection)


async def _seed_glossary(collection, terms: list[dict[str, str]]):
    """将默认术语表批量写入 ChromaDB。"""
    from .retriever import Retriever

    retriever = Retriever(collection)
    await retriever.add_terms(terms)


def _get_collection():
    """获取 ChromaDB collection（用于直接 CRUD 操作）。"""
    try:
        import chromadb
    except ImportError:
        return None

    if not DATA_DIR.exists():
        return None

    client = chromadb.PersistentClient(path=str(DATA_DIR))
    try:
        return client.get_collection(COLLECTION_NAME)
    except Exception:
        return None


def add_custom_terms(terms: list[dict[str, str]]) -> int:
    """添加自定义术语到知识库。返回成功添加的数量。"""
    collection = _get_collection()
    if collection is None:
        logger.warning("ChromaDB not available, cannot add terms")
        return 0

    from .retriever import Retriever
    import asyncio

    retriever = Retriever(collection)
    return asyncio.get_event_loop().run_until_complete(
        retriever.add_terms(terms)
    )


def search_terms(query: str, top_k: int = 10) -> list[dict]:
    """直接搜索术语（同步包装）。"""
    collection = _get_collection()
    if collection is None:
        return []

    from .retriever import Retriever
    import asyncio

    retriever = Retriever(collection)
    return asyncio.get_event_loop().run_until_complete(
        retriever.search_by_text(query, top_k)
    )


def get_stats() -> dict:
    """获取术语库统计信息。"""
    collection = _get_collection()
    if collection is None:
        return {"total_terms": 0, "domains": {}, "status": "unavailable"}

    count = collection.count()
    domains: dict[str, int] = {}
    try:
        all_data = collection.get(include=["metadatas"])
        if all_data["metadatas"]:
            for meta in all_data["metadatas"]:
                domain = meta.get("domain", "Other") if meta else "Other"
                domains[domain] = domains.get(domain, 0) + 1
    except Exception:
        pass

    return {
        "total_terms": count,
        "domains": domains,
        "status": "available",
    }
