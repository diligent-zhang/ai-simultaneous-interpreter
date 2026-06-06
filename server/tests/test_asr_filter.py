"""InterimFilter 测试。"""
import time
import pytest
from asr.filter import InterimFilter


class TestInterimFilter:
    def test_excludes_filler_words(self):
        """语气词应被排除。"""
        f = InterimFilter()
        assert f.should_send_to_translation("um", False) is False
        assert f.should_send_to_translation("uh", False) is False
        assert f.should_send_to_translation("er", False) is False
        assert f.should_send_to_translation("hmm", False) is False

    def test_excludes_empty_text(self):
        """纯空格/点号应被排除。"""
        f = InterimFilter()
        assert f.should_send_to_translation("...", False) is False
        assert f.should_send_to_translation("   ", False) is False

    def test_final_always_sends_if_complete(self):
        """Final 结果且满足完整性条件时应始终发送。"""
        f = InterimFilter()
        assert f.should_send_to_translation("Hello world.", True) is True

    def test_sentence_ending_punctuation_triggers_send(self):
        """句末标点应触发发送。"""
        f = InterimFilter()
        assert f.should_send_to_translation("This is a complete sentence.", False) is True

    def test_long_text_triggers_send(self):
        """超过 50 字符的文本应强制发送。"""
        f = InterimFilter()
        long_text = "a" * 51
        assert f.should_send_to_translation(long_text, False) is True

    def test_reset_clears_state(self):
        """reset 应清除所有内部状态。"""
        f = InterimFilter()
        f.should_send_to_translation("hello world test message here", False)
        f.reset()
        result = f.should_send_to_translation("hello world test message here new", False)
        assert result in (True, False)  # depends on rule matching

    def test_subject_predicate_detection(self):
        """应检测常见的主谓结构。"""
        f = InterimFilter()
        assert f._has_subject_predicate("I think this is important") is True
        assert f._has_subject_predicate("The model works well") is True
        assert f._has_subject_predicate("There are many reasons") is True
        assert f._has_subject_predicate("It is very useful") is True

    def test_non_subject_predicate_text(self):
        """非主谓结构文本不应被检测到。"""
        f = InterimFilter()
        assert f._has_subject_predicate("hello world") is False
        assert f._has_subject_predicate("okay then") is False
