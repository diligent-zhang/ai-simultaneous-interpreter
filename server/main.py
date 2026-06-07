"""AI 同声传译助手 — 后端入口。

接收音频帧 → Deepgram ASR → InterimFilter → RAG术语检索 → DeepSeek 翻译 → 双语字幕。
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import StreamingResponse
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
from session.context_window import ContextWindow

logger = logging.getLogger(__name__)


async def _safe_close(ws: WebSocket, code: int = 1000, reason: str = "") -> None:
    """安全关闭 WebSocket，忽略已关闭的连接。"""
    try:
        await ws.close(code=code, reason=reason)
    except RuntimeError:
        pass  # 连接已关闭，无需处理


async def _safe_send(ws: WebSocket, msg: dict) -> bool:
    """安全发送 WebSocket 消息，连接断开时返回 False。"""
    try:
        await ws.send_json(msg)
        return True
    except RuntimeError:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化 RAG，关闭时清理。"""
    if settings.RAG_ENABLED:
        try:
            from rag import init_rag
            await init_rag()
        except Exception as e:
            logger.warning("RAG init failed, continuing without RAG: %s", e)
    yield


app = FastAPI(
    title="AI Simultaneous Interpreter",
    version="0.4.0",
    description="AI 同声传译助手后端服务",
    lifespan=lifespan,
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
    return {"status": "ok", "version": "0.4.0"}


# ─── TTS API ────────────────────────────────────────────────────

@app.get("/api/tts")
async def tts_synthesize(
    text: str = Query(..., min_length=1, max_length=300),
    voice: str = Query(default="zh-CN-XiaoxiaoNeural"),
    rate: str = Query(default="+10%"),
):
    """流式 TTS 合成端点。返回 audio/mpeg 流。"""
    try:
        from tts.edge_provider import stream_synthesize
    except ImportError:
        raise HTTPException(status_code=503, detail="TTS service unavailable")

    return StreamingResponse(
        stream_synthesize(text, voice, rate),
        media_type="audio/mpeg",
        headers={"X-TTS-Provider": "edge"},
    )


# ─── Glossary API ───────────────────────────────────────────────

@app.get("/api/glossary/stats")
async def glossary_stats():
    """获取术语库统计信息。"""
    try:
        from rag.store import get_stats
        return get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glossary/search")
async def glossary_search(
    q: str = Query(..., min_length=1),
    top_k: int = Query(default=10, ge=1, le=50),
):
    """搜索术语。"""
    try:
        from rag.store import search_terms
        results = search_terms(q, top_k)
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/glossary/upload")
async def glossary_upload(data: dict):
    """上传自定义术语。

    Request body:
        {"terms": [{"en": "quantization", "zh": "量化", "domain": "AI"}, ...]}
    """
    terms = data.get("terms", [])
    if not terms:
        raise HTTPException(status_code=400, detail="No terms provided")

    try:
        from rag.store import add_custom_terms, get_stats
        imported = add_custom_terms(terms)
        stats = get_stats()
        return {
            "status": "ok",
            "imported": imported,
            "total": stats.get("total_terms", 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── WebSocket ──────────────────────────────────────────────────

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
    # Shared session context for term learning
    session_ctx = ContextWindow()
    correction_engine = CorrectionEngine(context=session_ctx) if settings.CORRECTION_ENABLED else None
    asr_active = bool(settings.DEEPGRAM_API_KEY)
    translation_active = bool(settings.DEEPSEEK_API_KEY)

    # Get RAG retriever if available
    retriever = None
    if settings.RAG_ENABLED:
        try:
            from rag import get_retriever
            retriever = get_retriever()
        except Exception:
            pass

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

        interim_filter = InterimFilter()
        reconnect_attempt = 0
        MAX_RECONNECT = 5  # 最多重连 5 次，避免无限循环

        # ── 外层重连循环：Deepgram 断开后自动恢复 ─
        while reconnect_attempt < MAX_RECONNECT:
            try:
                # 首帧或重连：等待音频数据
                if reconnect_attempt == 0:
                    logger.debug("Waiting for first audio frame before Deepgram connect")
                else:
                    logger.info("ASR reconnecting (attempt %d/%d)...", reconnect_attempt + 1, MAX_RECONNECT)
                    await _safe_send(ws, StatusMessage(
                        asr_status="reconnecting", translation_status="connected", latency_ms=0,
                    ).model_dump())

                first_chunk = await audio_queue.get()
                if first_chunk is None:
                    return

                provider = DeepgramProvider(api_key=settings.DEEPGRAM_API_KEY)
                interim_filter.reset()

                # 用 asyncio.Queue 包装，把首帧放回去
                wrapped_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
                wrapped_queue.put_nowait(first_chunk)

                # 后台搬运原始队列到包装队列
                async def bridge():
                    while True:
                        chunk = await audio_queue.get()
                        wrapped_queue.put_nowait(chunk)
                        if chunk is None:
                            break

                bridge_task = asyncio.create_task(bridge())

                try:
                    async for result in provider.stream_transcribe(wrapped_queue, asr_config):
                        # 连接成功，重置重连计数
                        reconnect_attempt = 0

                        segment_counter += 1
                        seg_id = f"seg_{segment_counter:04d}"

                        asr_msg = SubtitleMessage(
                            segment_id=seg_id,
                            text=result.text,
                            is_final=result.is_final,
                            source="asr",
                            confidence=result.confidence,
                            timestamp=time.time(),
                            replace=not result.is_final,
                            sequence=segment_counter,
                        )
                        await _safe_send(ws, asr_msg.model_dump())

                        if translation_active and interim_filter.should_send_to_translation(
                            result.text, result.is_final
                        ):
                            translation_queue.put_nowait((result.text, result.is_final))

                    # stream_transcribe 正常结束（Deepgram 关闭了连接）
                    logger.warning("Deepgram connection closed, will reconnect...")
                    reconnect_attempt += 1
                    await asyncio.sleep(1.0)  # 短暂等待后重连

                finally:
                    bridge_task.cancel()
                    try:
                        await bridge_task
                    except asyncio.CancelledError:
                        pass

            except Exception as e:
                logger.exception("ASR pipeline error: %s (attempt %d)", e, reconnect_attempt + 1)
                reconnect_attempt += 1
                await _safe_send(ws, StatusMessage(
                    asr_status="error", translation_status="idle", latency_ms=0,
                ).model_dump())
                await asyncio.sleep(2.0)  # 错误后等待 2 秒再重连

        logger.error("ASR max reconnect attempts reached, giving up")
        await _safe_send(ws, StatusMessage(
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
                retriever=retriever,
            )
            context = TranslationContext()
            trans_seq = 0  # 独立递增翻译计数器
            _last_translated = ""  # 去重：上次翻译的原文

            while True:
                item = await translation_queue.get()
                if item is None:
                    break

                text, is_final = item

                # ── 翻译去重：跳过与上次相同的原文 ──
                if text == _last_translated and not is_final:
                    continue
                _last_translated = text
                try:
                    trans_seq += 1
                    # 固定 segment_id：同一次翻译请求的 partial/final 共用
                    trans_seg_id = f"trans_{trans_seq:04d}"
                    partial_seq = 0

                    async for trans_result in provider.stream_translate(
                        text, context, trans_config, session_glossary=session_ctx
                    ):
                        if trans_result.finish_reason == "wait":
                            break

                        partial_seq += 1

                        if trans_result.text:
                            is_partial = trans_result.is_partial
                            trans_msg = SubtitleMessage(
                                segment_id=trans_seg_id,
                                text=trans_result.text,
                                is_final=not is_partial,
                                source="translation",
                                confidence=0.9,
                                timestamp=time.time(),
                                replace=is_partial,      # partial → 前端替换同行
                                sequence=partial_seq,
                            )
                            await ws.send_json(trans_msg.model_dump())

                    if trans_result.text and trans_result.finish_reason == "stop":
                        context.recent_sentences.append(trans_result.text)
                        if len(context.recent_sentences) > 3:
                            context.recent_sentences.pop(0)

                        if correction_engine:
                            try:
                                corr_events = correction_engine.process_translation(
                                    trans_seg_id, text, trans_result.text
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
            await _safe_send(ws, StatusMessage(
                asr_status="connected", translation_status="error", latency_ms=0,
            ).model_dump())

    try:
        await _safe_send(ws, StatusMessage(
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
    except RuntimeError as e:
        if "disconnect" in str(e).lower():
            logger.info("Client disconnected (RuntimeError)")
        else:
            logger.exception("Unexpected RuntimeError")
            await _safe_close(ws, code=1011, reason="Internal server error")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Invalid message: %s", e)
        await _safe_close(ws, code=1003, reason="Invalid message format")
    except Exception:
        logger.exception("Unexpected error")
        await _safe_close(ws, code=1011, reason="Internal server error")
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
