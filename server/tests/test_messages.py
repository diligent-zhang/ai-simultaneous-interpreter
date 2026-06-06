"""WebSocket 消息模型验证测试。"""
import pytest
from pydantic import ValidationError
from models.messages import (
    ConfigMessage,
    PingMessage,
    PongMessage,
    SubtitleMessage,
    StatusMessage,
    EchoMessage,
)


class TestConfigMessage:
    def test_default_values(self):
        msg = ConfigMessage()
        assert msg.type == "config"
        assert msg.source_lang == "en"
        assert msg.target_lang == "zh"
        assert msg.asr_provider == "deepgram"
        assert msg.translation_provider == "deepseek"

    def test_custom_values(self):
        msg = ConfigMessage(
            source_lang="ja",
            target_lang="en",
            asr_provider="azure",
            translation_provider="openai",
        )
        assert msg.source_lang == "ja"
        assert msg.target_lang == "en"


class TestPingPong:
    def test_ping_message(self):
        msg = PingMessage()
        assert msg.type == "ping"

    def test_pong_message(self):
        msg = PongMessage()
        assert msg.type == "pong"


class TestSubtitleMessage:
    def test_valid_subtitle(self):
        msg = SubtitleMessage(
            segment_id="seg_001",
            text="Hello world",
            is_final=True,
            source="asr",
            confidence=0.95,
            timestamp=1234567890.0,
        )
        assert msg.type == "subtitle"
        assert msg.segment_id == "seg_001"
        assert msg.confidence == 0.95

    def test_confidence_bounds(self):
        """置信度应在 0-1 范围内。"""
        msg = SubtitleMessage(segment_id="seg_001", text="test", confidence=0.5)
        assert 0.0 <= msg.confidence <= 1.0

    def test_confidence_out_of_bounds_raises(self):
        """置信度超出范围应抛出验证错误。"""
        with pytest.raises(ValidationError):
            SubtitleMessage(segment_id="seg_001", text="test", confidence=1.5)

    def test_negative_confidence_raises(self):
        """负置信度应抛出验证错误。"""
        with pytest.raises(ValidationError):
            SubtitleMessage(segment_id="seg_001", text="test", confidence=-0.1)

    def test_source_values(self):
        """source 字段应接受 asr 和 translation。"""
        asr_msg = SubtitleMessage(segment_id="s1", text="hello", source="asr")
        assert asr_msg.source == "asr"
        trans_msg = SubtitleMessage(segment_id="s1", text="你好", source="translation")
        assert trans_msg.source == "translation"


class TestStatusMessage:
    def test_default_values(self):
        msg = StatusMessage()
        assert msg.type == "status"
        assert msg.asr_status == "idle"
        assert msg.translation_status == "idle"
        assert msg.latency_ms == 0

    def test_connected_status(self):
        msg = StatusMessage(
            asr_status="connected", translation_status="connected", latency_ms=850
        )
        assert msg.latency_ms == 850
        d = msg.model_dump()
        assert d["latency_ms"] == 850


class TestEchoMessage:
    def test_echo_message(self):
        msg = EchoMessage(original_size=640)
        assert msg.type == "echo"
        assert msg.original_size == 640
        assert msg.message == "audio frame received"
