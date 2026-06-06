"""ConflictDetector 测试。"""
import pytest
from correction.detector import ConflictDetector


class TestConflictDetector:
    def test_detect_term_inconsistency_empty_glossary(self):
        """空术语表不应产生冲突。"""
        d = ConflictDetector()
        conflicts = d.detect_term_inconsistency("the transformer model works", {})
        assert conflicts == []

    def test_detect_pronoun_ambiguity_found(self):
        """含代词的文本应被检测到指代模糊。"""
        d = ConflictDetector()
        assert d.detect_pronoun_ambiguity("It works well in practice") is True
        assert d.detect_pronoun_ambiguity("They showed great results") is True
        assert d.detect_pronoun_ambiguity("This is important") is True

    def test_detect_pronoun_ambiguity_not_found(self):
        """无代词的文本不应触发。"""
        d = ConflictDetector()
        assert d.detect_pronoun_ambiguity("The model achieves high accuracy") is False
        assert d.detect_pronoun_ambiguity("Deep learning transforms industries") is False

    def test_detect_semantic_gap_empty_prev(self):
        """前文为空时不应触发语义断裂（没有前文可比较）。"""
        d = ConflictDetector()
        assert d.detect_semantic_gap("", "ab") is False

    def test_detect_semantic_gap_normal(self):
        """正常长度的文本不应触发语义断裂。"""
        d = ConflictDetector()
        assert d.detect_semantic_gap("前一句翻译内容", "正常的中文翻译") is False
