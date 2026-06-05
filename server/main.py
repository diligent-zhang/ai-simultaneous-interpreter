"""AI 同声传译助手 — 后端入口。

Slice 1: 基础 WebSocket 连通性验证。
接收音频帧，回显确认消息。
"""

import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.messages import (
    ConfigMessage,
    EchoMessage,
    PingMessage,
    PongMessage,
    StatusMessage,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Simultaneous Interpreter",
    version="0.1.0",
    description="AI 同声传译助手后端服务",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
    logger.info("Client connected")

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
                logger.debug("Audio frame received: %d bytes", len(audio_bytes))

            elif "text" in data:
                # JSON 控制消息
                msg = json.loads(data["text"])
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    PingMessage.model_validate(msg)
                    pong = PongMessage()
                    await ws.send_json(pong.model_dump())

                elif msg_type == "config":
                    ConfigMessage.model_validate(msg)
                    # Slice 1 仅打印配置，后续切片使用
                    logger.info("Config received: %s", msg)
                    status = StatusMessage()
                    await ws.send_json(status.model_dump())

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Invalid message received: %s", e)
        await ws.close(code=1003, reason="Invalid message format")
    except Exception:
        logger.exception("Unexpected error in WebSocket handler")
        await ws.close(code=1011, reason="Internal server error")


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
