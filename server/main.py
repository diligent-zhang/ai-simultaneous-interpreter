"""AI 同声传译助手 — 后端入口。

Slice 2: Deepgram 流式 ASR 集成。
接收音频帧 → Deepgram 识别 → 推送字幕消息。
"""

import asyncio
import json
import logging
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.messages import (
    ConfigMessage,
    PingMessage,
    PongMessage,
    StatusMessage,
    SubtitleMessage,
)
from asr.types import ASRConfig, ASRResult
from asr.deepgram_provider import DeepgramProvider

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Simultaneous Interpreter",
    version="0.2.0",
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
    return {"status": "ok", "version": "0.2.0"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """主 WebSocket 端点。

    接收 PCM 音频帧 → Deepgram 流式识别 → 推送 SubtitleMessage。
    支持 JSON 控制消息 (config, ping)。
    """
    await ws.accept()
    logger.info("Client connected")

    # 每个客户端独立的音频队列和 ASR 状态
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    asr_task: asyncio.Task | None = None
    asr_config = ASRConfig(
        language=settings.DEEPGRAM_LANGUAGE,
        model=settings.DEEPGRAM_MODEL,
        sample_rate=settings.DEEPGRAM_SAMPLE_RATE,
    )
    segment_counter = 0

    async def run_asr():
        """ASR 协程：消费音频帧 → Deepgram → 推送字幕。"""
        nonlocal segment_counter

        if not settings.DEEPGRAM_API_KEY:
            logger.warning("DEEPGRAM_API_KEY not set, falling back to echo mode")
            # 降级：无 API Key 时回显
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                echo_msg = SubtitleMessage(
                    segment_id=f"echo_{segment_counter}",
                    text=f"[Echo] {len(chunk)} bytes audio frame",
                    is_final=False,
                    source="asr",
                    timestamp=time.time(),
                )
                segment_counter += 1
                await ws.send_json(echo_msg.model_dump())
            return

        try:
            provider = DeepgramProvider(api_key=settings.DEEPGRAM_API_KEY)
            async for result in provider.stream_transcribe(audio_queue, asr_config):
                segment_counter += 1
                segment_id = f"seg_{segment_counter:04d}"

                subtitle = SubtitleMessage(
                    segment_id=segment_id,
                    text=result.text,
                    is_final=result.is_final,
                    source="asr",
                    confidence=result.confidence,
                    timestamp=time.time(),
                )
                await ws.send_json(subtitle.model_dump())
                logger.debug(
                    "Subtitle sent: id=%s final=%s text=%s",
                    segment_id, result.is_final, result.text[:50],
                )
        except Exception as e:
            logger.exception("ASR pipeline error: %s", e)
            status = StatusMessage(
                asr_status="error",
                translation_status="idle",
                latency_ms=0,
            )
            await ws.send_json(status.model_dump())

    try:
        # 发送就绪状态
        ready_status = StatusMessage(
            asr_status="connected" if settings.DEEPGRAM_API_KEY else "idle",
            translation_status="idle",
            latency_ms=0,
        )
        await ws.send_json(ready_status.model_dump())

        # 启动 ASR 协程
        asr_task = asyncio.create_task(run_asr())

        # 主循环：接收消息
        while True:
            data = await ws.receive()

            if "bytes" in data:
                # 音频帧 → 入队
                audio_bytes = data["bytes"]
                audio_queue.put_nowait(audio_bytes)

            elif "text" in data:
                msg = json.loads(data["text"])
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    PingMessage.model_validate(msg)
                    pong = PongMessage()
                    await ws.send_json(pong.model_dump())

                elif msg_type == "config":
                    ConfigMessage.model_validate(msg)
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
    finally:
        # 清理：发送 None 停止音频转发，取消 ASR 任务
        audio_queue.put_nowait(None)
        if asr_task:
            asr_task.cancel()
            try:
                await asr_task
            except asyncio.CancelledError:
                pass


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
