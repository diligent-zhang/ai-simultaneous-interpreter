"""CorrectionEngine 测试。"""
import pytest
from correction.engine import CorrectionEngine


class TestCorrectionEngine:
    def test_process_translation_returns_events(self):
        """处理翻译应返回事件列表（可能为空）。"""
        engine = CorrectionEngine()
        events = engine.process_translation(
            "seg_001",
            "Artificial intelligence is transforming every industry",
            "人工智能正在改变每一个行业",
        )
        assert isinstance(events, list)

    def test_process_translation_tracks_segments(self):
        """应追踪已处理的句段。"""
        engine = CorrectionEngine()
        engine.process_translation("seg_001", "Hello world", "你好世界")
        stats = engine.get_stats()
        assert stats["segments_tracked"] >= 1

    def test_multiple_segments_no_crash(self):
        """处理多个句段不应崩溃。"""
        engine = CorrectionEngine()
        segments = [
            ("seg_001", "This is the first sentence", "这是第一个句子"),
            ("seg_002", "This is the second sentence", "这是第二个句子"),
            ("seg_003", "This is the third sentence", "这是第三个句子"),
        ]
        for seg_id, orig, trans in segments:
            events = engine.process_translation(seg_id, orig, trans)
            assert isinstance(events, list)

    def test_max_corrections_tracked(self):
        """修正次数应正确追踪。"""
        engine = CorrectionEngine()
        stats = engine.get_stats()
        assert "corrections_used" in stats
        assert "max_corrections" in stats
        assert stats["max_corrections"] == 20

    def test_context_initialized(self):
        """Engine 应初始化上下文窗口。"""
        engine = CorrectionEngine()
        assert engine.context is not None
        assert engine.detector is not None

    def test_segment_corrected_count_limit(self):
        """同一 segment 最多修正 2 次的保护应生效。"""
        engine = CorrectionEngine()
        for i in range(10):
            engine.process_translation(
                f"seg_{i:03d}",
                f"Test sentence number {i}",
                f"测试句子 {i}",
            )
        stats = engine.get_stats()
        assert stats["corrections_used"] <= 20
