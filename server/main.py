"""AI 同声传译助手 — 后端入口。

Slice 1: 基础 WebSocket 连通性验证。
接收音频帧，回显确认消息。
"""

import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.messages import EchoMessage, PongMessage

app = FastAPI(
    title="AI Simultaneous Interpreter",
    version="0.1.0",
    description="AI 同声传译助手后端服务",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """健康检查端点。"""
    return {"status": "ok", "version": "0.1.0"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """主 WebSocket 端点。

    支持:
    - 二进制音频帧 (PCM 16kHz 16bit mono)
    - JSON 控制消息 (config, ping)
    """
    await ws.accept()
    print(f"[WS] Client connected")

    try:
        while True:
            # 接收消息：二进制（音频帧）或文本（JSON 控制消息）
            data = await ws.receive()

            if "bytes" in data:
                # 二进制音频帧 → 回显确认
                audio_bytes = data["bytes"]
                echo = EchoMessage(
                    original_size=len(audio_bytes),
                    message=f"audio frame received: {len(audio_bytes)} bytes",
                )
                await ws.send_json(echo.model_dump())

            elif "text" in data:
                # JSON 控制消息
                msg = json.loads(data["text"])
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    pong = PongMessage()
                    await ws.send_json(pong.model_dump())

                elif msg_type == "config":
                    # Slice 1 仅打印配置，后续切片使用
                    print(f"[WS] Config received: {msg}")
                    status = {
                        "type": "status",
                        "asr_status": "idle",
                        "translation_status": "idle",
                        "latency_ms": 0,
                    }
                    await ws.send_json(status)

    except WebSocketDisconnect:
        print(f"[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")
        await ws.close(code=1011, reason=str(e))


def main():
    """启动服务。"""
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
