"""Translator tools 测试 — 术语提取与上下文构建。"""
import pytest
from translator.tools import (
    extract_term_candidates,
    format_glossary_context,
)


class TestExtractTermCandidates:
    def test_extracts_capitalized_phrases(self):
        """应提取大写短语。"""
        text = "We use Reinforcement Learning and Natural Language Processing"
        candidates = extract_term_candidates(text)
        candidates_lower = [c.lower() for c in candidates]
        has_rl = "reinforcement learning" in candidates_lower
        has_nlp = "natural language processing" in candidates_lower
        assert has_rl or has_nlp

    def test_extracts_technical_terms(self):
        """应提取技术术语。"""
        text = "The deep learning model uses neural networks"
        candidates = extract_term_candidates(text)
        candidates_lower = [c.lower() for c in candidates]
        has_dl = "deep learning" in candidates_lower
        has_nn = "neural networks" in candidates_lower
        assert has_dl or has_nn

    def test_excludes_stop_words(self):
        """应排除常见停用词。"""
        text = "The and for that this with from"
        candidates = extract_term_candidates(text)
        for c in candidates:
            assert c.lower() not in {"the", "and", "for", "that"}

    def test_excludes_short_terms(self):
        """应排除过短的词 (<3 字符)。"""
        text = "AI is OK"
        candidates = extract_term_candidates(text)
        for c in candidates:
            assert len(c) >= 3

    def test_returns_list_for_plain_text(self):
        """普通文本返回列表。"""
        text = "hello world"
        candidates = extract_term_candidates(text)
        assert isinstance(candidates, list)

    def test_limits_to_20_candidates(self):
        """候选词数量不超过 20。"""
        text = " ".join([
            "The Transformer model uses",
            "Self Attention mechanisms for",
            "Natural Language Processing tasks",
            "Reinforcement Learning from Human Feedback is",
            "also known as RLHF and helps with",
            "Large Language Model alignment",
            "Deep Learning and Machine Learning",
            "Computer Vision applications include",
            "Generative Adversarial Networks and",
            "Convolutional Neural Networks",
            "Recurrent Neural Networks like",
            "Long Short Term Memory networks",
            "Vision Transformers CLIP models",
            "Mixture of Experts architecture",
            "Low Rank Adaptation techniques",
        ])
        candidates = extract_term_candidates(text)
        assert len(candidates) <= 20


class TestFormatGlossaryContext:
    def test_formats_single_term(self):
        """应正确格式化单个术语。"""
        matches = [{"en": "LLM", "zh": "大语言模型"}]
        result = format_glossary_context(matches)
        assert "LLM" in result
        assert "大语言模型" in result

    def test_formats_multiple_terms(self):
        """应正确格式化多个术语。"""
        matches = [
            {"en": "LLM", "zh": "大语言模型"},
            {"en": "RLHF", "zh": "基于人类反馈的强化学习"},
        ]
        result = format_glossary_context(matches)
        assert "LLM" in result
        assert "RLHF" in result

    def test_empty_matches_returns_empty_string(self):
        """空匹配应返回空字符串。"""
        assert format_glossary_context([]) == ""

    def test_skips_incomplete_entries(self):
        """缺少 en 或 zh 的条目应被跳过。"""
        matches = [
            {"en": "", "zh": "翻译"},
            {"en": "LLM", "zh": "大语言模型"},
        ]
        result = format_glossary_context(matches)
        assert "LLM" in result
