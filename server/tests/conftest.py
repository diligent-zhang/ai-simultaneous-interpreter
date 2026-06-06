"""共享 fixtures。"""
import pytest


@pytest.fixture
def sample_english_text():
    """返回一段典型的英文技术演讲文本。"""
    return "Artificial intelligence is transforming every industry today."


@pytest.fixture
def sample_chinese_translation():
    """返回对应的中文翻译。"""
    return "人工智能正在改变当今的每一个行业。"
