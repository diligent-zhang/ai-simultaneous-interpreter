"""会话即时学习测试。"""
import pytest
from session.context_window import ContextWindow


class TestContextWindowTermLearning:
    def test_extract_terms_from_simple_sentence(self):
        """应从简单句提取术语。"""
        ctx = ContextWindow()
        count = ctx.extract_terms(
            "The Transformer model achieves great results",
            "Transformer 模型取得了很好的结果",
        )
        assert count >= 1

    def test_extract_terms_skips_stop_words(self):
        """应跳过停用词。"""
        ctx = ContextWindow()
        count = ctx.extract_terms(
            "The and for that this with",
            "这些停用词不应收录",
        )
        assert "the" not in {k.lower() for k in ctx.glossary}

    def test_search_glossary_finds_match(self):
        """search_glossary 应找到匹配术语。"""
        ctx = ContextWindow()
        ctx.add_term("transformer", "Transformer 模型")
        results = ctx.search_glossary("transformer")
        assert len(results) >= 1
        assert results[0]["en"] == "transformer"
        assert results[0]["source"] == "session"

    def test_search_glossary_substring_match(self):
        """应支持子串匹配。"""
        ctx = ContextWindow()
        ctx.add_term("machine learning", "机器学习")
        results = ctx.search_glossary("learning")
        assert len(results) >= 1

    def test_search_glossary_no_match(self):
        """无匹配时应返回空列表。"""
        ctx = ContextWindow()
        ctx.add_term("transformer", "Transformer 模型")
        results = ctx.search_glossary("quantum computing")
        assert results == []

    def test_glossary_lru_eviction(self):
        """LRU 淘汰应生效（上限 50 条）。"""
        ctx = ContextWindow()
        for i in range(60):
            ctx.add_term(f"term_{i}", f"术语_{i}")
        assert len(ctx.glossary) <= 50

    def test_extract_terms_deduplication(self):
        """重复术语不应增加总数（LRU 移到末尾）。"""
        ctx = ContextWindow()
        original = "Machine Learning is important"
        translation = "机器学习很重要"
        ctx.extract_terms(original, translation)
        before = len(ctx.glossary)
        ctx.extract_terms(original, translation)
        assert len(ctx.glossary) == before

    def test_context_get_context_for_prompt(self):
        """get_context_for_prompt 应包含 session glossary。"""
        ctx = ContextWindow()
        ctx.add_term("transformer", "Transformer 模型")
        ctx.add_sentence("Hello world", "你好世界")
        prompt_context = ctx.get_context_for_prompt()
        assert "transformer" in prompt_context
        assert "Transformer 模型" in prompt_context
