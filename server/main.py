"""AI 同声传译助手 — 后端入口。

Slice 3: DeepSeek 流式翻译集成。
接收音频帧 → Deepgram ASR → InterimFilter → DeepSeek 翻译 → 双语字幕。
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
from asr.types import ASRConfig
from asr.filter import InterimFilter
from asr.deepgram_provider import DeepgramProvider
from translator.types import TranslationConfig, TranslationContext
from translator.deepseek_provider import DeepSeekProvider
from correction.engine import CorrectionEngine

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Simultaneous Interpreter",
    version="0.3.0",
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
    return {"status": "ok", "version": "0.3.0"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("Client connected")

    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    translation_queue: asyncio.Queue[tuple[str, bool] | None] = asyncio.Queue()
    asr_task: asyncio.Task | None = None
    translation_task: asyncio.Task | None = None

    asr_config = ASRConfig(
        language=settings.DEEPGRAM_LANGUAGE,
        model=settings.DEEPGRAM_MODEL,
        sample_rate=settings.DEEPGRAM_SAMPLE_RATE,
    )
    trans_config = TranslationConfig(
        model=settings.DEEPSEEK_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_MAX_TOKENS,
    )

    segment_counter = 0
    # 修正引擎 Sidecar
    correction_engine = CorrectionEngine() if settings.CORRECTION_ENABLED else None
    asr_active = bool(settings.DEEPGRAM_API_KEY)
    translation_active = bool(settings.DEEPSEEK_API_KEY)

    async def run_asr():
        nonlocal segment_counter

        if not asr_active:
            logger.warning("DEEPGRAM_API_KEY not set, falling back to echo")
            await ws.send_json(StatusMessage(
                asr_status="idle", translation_status="idle", latency_ms=0,
            ).model_dump())
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                msg = SubtitleMessage(
                    segment_id=f"echo_{segment_counter}",
                    text=f"[Echo] {len(chunk)} bytes",
                    is_final=False, source="asr", timestamp=time.time(),
                )
                segment_counter += 1
                await ws.send_json(msg.model_dump())
            return

        try:
            provider = DeepgramProvider(api_key=settings.DEEPGRAM_API_KEY)
            interim_filter = InterimFilter()

            async for result in provider.stream_transcribe(audio_queue, asr_config):
                segment_counter += 1
                seg_id = f"seg_{segment_counter:04d}"

                # 1. Push ASR English text to frontend
                asr_msg = SubtitleMessage(
                    segment_id=seg_id,
                    text=result.text,
                    is_final=result.is_final,
                    source="asr",
                    confidence=result.confidence,
                    timestamp=time.time(),
                )
                await ws.send_json(asr_msg.model_dump())

                # 2. Filter → enqueue for translation
                if translation_active and interim_filter.should_send_to_translation(
                    result.text, result.is_final
                ):
                    translation_queue.put_nowait((result.text, result.is_final))

        except Exception as e:
            logger.exception("ASR pipeline error: %s", e)
            await ws.send_json(StatusMessage(
                asr_status="error", translation_status="idle", latency_ms=0,
            ).model_dump())

    async def run_translation():
        if not translation_active:
            logger.warning("DEEPSEEK_API_KEY not set, translation disabled")
            await ws.send_json(StatusMessage(
                asr_status="connected", translation_status="idle", latency_ms=0,
            ).model_dump())
            return

        try:
            provider = DeepSeekProvider(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
            )
            context = TranslationContext()

            while True:
                item = await translation_queue.get()
                if item is None:
                    break

                text, is_final = item
                try:
                    last_sent = ""
                    async for trans_result in provider.stream_translate(
                        text, context, trans_config
                    ):
                        if trans_result.finish_reason == "wait":
                            break
                        if trans_result.text == last_sent and trans_result.is_partial:
                            continue
                        last_sent = trans_result.text

                        if trans_result.text:
                            trans_msg = SubtitleMessage(
                                segment_id=f"trans_{segment_counter:04d}",
                                text=trans_result.text,
                                is_final=not trans_result.is_partial,
                                source="translation",
                                confidence=0.9,
                                timestamp=time.time(),
                            )
                            await ws.send_json(trans_msg.model_dump())

                    if trans_result.text and trans_result.finish_reason == "stop":
                        context.recent_sentences.append(trans_result.text)
                        if len(context.recent_sentences) > 3:
                            context.recent_sentences.pop(0)

                        # Sidecar: 修正引擎
                        if correction_engine:
                            try:
                                seg_id = f"seg_{segment_counter:04d}"
                                corr_events = correction_engine.process_translation(
                                    seg_id, text, trans_result.text
                                )
                                for event in corr_events:
                                    await ws.send_json({
                                        "type": "correction",
                                        "segment_id": event.segment_id,
                                        "old_text": event.old_text,
                                        "new_text": event.new_text,
                                        "reason": event.reason.value,
                                        "confidence": event.confidence,
                                    })
                            except Exception as e:
                                logger.error("Correction engine error: %s", e)

                except Exception as e:
                    logger.error("Translation error for text '%s': %s", text[:30], e)
        except Exception as e:
            logger.exception("Translation pipeline error: %s", e)

    try:
        await ws.send_json(StatusMessage(
            asr_status="connected" if asr_active else "idle",
            translation_status="connected" if translation_active else "idle",
            latency_ms=0,
        ).model_dump())

        asr_task = asyncio.create_task(run_asr())
        if translation_active:
            translation_task = asyncio.create_task(run_translation())

        while True:
            data = await ws.receive()

            if "bytes" in data:
                audio_queue.put_nowait(data["bytes"])

            elif "text" in data:
                msg = json.loads(data["text"])
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    PingMessage.model_validate(msg)
                    await ws.send_json(PongMessage().model_dump())
                elif msg_type == "config":
                    ConfigMessage.model_validate(msg)
                    logger.info("Config received: %s", msg)
                    await ws.send_json(StatusMessage().model_dump())

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Invalid message: %s", e)
        await ws.close(code=1003, reason="Invalid message format")
    except Exception:
        logger.exception("Unexpected error")
        await ws.close(code=1011, reason="Internal server error")
    finally:
        audio_queue.put_nowait(None)
        translation_queue.put_nowait(None)
        for task in [asr_task, translation_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


def main():
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)


if __name__ == "__main__":
    main()
