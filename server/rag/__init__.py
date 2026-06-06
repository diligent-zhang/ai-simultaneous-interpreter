"""RAG 知识库模块 — 术语检索与上下文注入。

初始化流程:
    from rag import init_rag, get_retriever
    await init_rag()  # 服务启动时调用一次
    retriever = get_retriever()  # 后续在翻译管线中使用
"""
import logging

logger = logging.getLogger(__name__)

_retriever = None


async def init_rag():
    """初始化 RAG 知识库。应在服务启动时调用。"""
    global _retriever
    try:
        from .store import create_retriever
        _retriever = await create_retriever()
        logger.info("RAG knowledge base initialized")
    except Exception as e:
        logger.warning("RAG initialization failed: %s, acronym-only fallback", e)
        _retriever = None


def get_retriever():
    """获取检索器实例。可能为 None（RAG 不可用时）。"""
    return _retriever
