"""Edge TTS 测试。"""
import pytest


class TestEdgeTTSProvider:
    def test_import(self):
        """模块应能正常导入。"""
        from tts.edge_provider import stream_synthesize, DEFAULT_VOICE
        assert DEFAULT_VOICE == "zh-CN-XiaoxiaoNeural"

    def test_stream_synthesize(self):
        """应能流式合成音频并产出 bytes chunk。"""
        import asyncio
        from tts.edge_provider import stream_synthesize

        async def run():
            chunks = []
            async for chunk in stream_synthesize("你好"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.get_event_loop().run_until_complete(run())
        assert len(chunks) > 0
        assert all(isinstance(c, bytes) for c in chunks)

    def test_alt_voices_available(self):
        """备用音色应可用。"""
        from tts.edge_provider import ALT_VOICES
        assert len(ALT_VOICES) >= 2


class TestTTSEndpoint:
    def test_tts_endpoint_returns_audio(self):
        """TTS 端点应返回 audio/mpeg。"""
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.get("/api/tts?text=测试")
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            assert "audio" in response.headers.get("content-type", "")

    def test_tts_empty_text_rejected(self):
        """空文本应被拒绝。"""
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.get("/api/tts?text=")
        assert response.status_code == 422

    def test_tts_long_text_accepted(self):
        """300 字以内应被接受。"""
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.get("/api/tts?text=" + "测试" * 100)
        assert response.status_code in [200, 503]
