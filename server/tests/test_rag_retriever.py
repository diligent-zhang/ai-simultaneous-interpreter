"""RAG Retriever 测试 — 需要 chromadb 可用。"""
import pytest

chromadb = pytest.importorskip("chromadb", reason="chromadb not installed")


class TestRetriever:
    def test_create_retriever(self):
        """应能创建 Retriever 实例。"""
        client = chromadb.Client()
        collection = client.create_collection("test_glossary")
        from rag.retriever import Retriever
        retriever = Retriever(collection)
        assert retriever is not None

    def test_add_and_search_terms(self):
        """添加术语后应能检索到。"""
        import asyncio
        client = chromadb.Client()
        collection = client.create_collection("test_add_search")

        from rag.retriever import Retriever
        retriever = Retriever(collection)

        terms = [
            {"en": "test transformer", "zh": "测试 Transformer", "domain": "AI"},
            {"en": "test embedding", "zh": "测试嵌入", "domain": "AI"},
        ]
        count = asyncio.get_event_loop().run_until_complete(
            retriever.add_terms(terms)
        )
        assert count >= 1

        results = asyncio.get_event_loop().run_until_complete(
            retriever.search(["test transformer"], top_k=5, threshold=0.0)
        )
        assert len(results) >= 1

    def test_search_empty_queries(self):
        """空查询应返回空结果。"""
        import asyncio
        client = chromadb.Client()
        collection = client.create_collection("test_empty")

        from rag.retriever import Retriever
        retriever = Retriever(collection)
        results = asyncio.get_event_loop().run_until_complete(
            retriever.search([], top_k=5)
        )
        assert results == []

    def test_search_by_text(self):
        """文本搜索应返回结果。"""
        import asyncio
        client = chromadb.Client()
        collection = client.create_collection("test_text_search")

        from rag.retriever import Retriever
        retriever = Retriever(collection)
        terms = [
            {"en": "test machine learning", "zh": "测试机器学习", "domain": "AI"},
        ]
        asyncio.get_event_loop().run_until_complete(
            retriever.add_terms(terms)
        )

        results = asyncio.get_event_loop().run_until_complete(
            retriever.search_by_text("machine learning", top_k=3)
        )
        assert isinstance(results, list)
