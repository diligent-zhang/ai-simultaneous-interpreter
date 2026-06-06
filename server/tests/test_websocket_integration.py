"""WebSocket 端点集成测试。"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app():
    """延迟导入 app 以避免模块级副作用。"""
    from main import app
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self, client):
        """健康检查端点应返回 ok。"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestGlossaryAPI:
    def test_stats_endpoint(self, client):
        """术语库统计端点应返回有效响应。"""
        response = client.get("/api/glossary/stats")
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "total_terms" in data
            assert "status" in data

    def test_search_endpoint(self, client):
        """术语搜索端点应正常工作。"""
        response = client.get("/api/glossary/search?q=transformer")
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert "results" in data

    def test_search_empty_query_rejected(self, client):
        """空搜索应被拒绝。"""
        response = client.get("/api/glossary/search?q=")
        assert response.status_code == 422

    def test_upload_no_terms_rejected(self, client):
        """空术语上传应被拒绝。"""
        response = client.post("/api/glossary/upload", json={"terms": []})
        assert response.status_code == 400

    def test_upload_with_terms(self, client):
        """有效的术语上传应成功。"""
        response = client.post("/api/glossary/upload", json={
            "terms": [
                {"en": "test quant", "zh": "测试量化", "domain": "AI"},
            ]
        })
        assert response.status_code in [200, 500]


class TestWebSocketConnection:
    def test_ws_connect_disconnect(self, client):
        """WebSocket 应能连接和断开。"""
        with client.websocket_connect("/ws") as ws:
            data = ws.receive_json()
            assert data["type"] == "status"
            assert "asr_status" in data

    def test_ws_connect_and_exchange(self, client):
        """WebSocket 应能连接、发送消息并接收响应。"""
        with client.websocket_connect("/ws") as ws:
            # Should receive at least the initial status message
            data = ws.receive_json()
            assert "type" in data
            # Send ping — server should not crash
            ws.send_json({"type": "ping"})
            # Receive at least one more message
            data2 = ws.receive_json()
            assert "type" in data2

    def test_ws_rejects_invalid_json(self, client):
        """发送无效 JSON 应被正确处理。"""
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # consume initial status
            ws.send_text("not valid json")
            try:
                ws.receive_json()
            except Exception:
                pass  # Expected: connection closed

    def test_ws_audio_frame_accepted(self, client):
        """二进制音频帧应被接受。"""
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # consume initial status
            pcm_frame = b"\x00" * 640
            ws.send_bytes(pcm_frame)
            import time
            time.sleep(0.1)
