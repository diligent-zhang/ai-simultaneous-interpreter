"""Deepgram 流式 ASR 实现。

使用 deepgram-sdk v3 的 listen.websocket() 方法，
通过 asyncio.Queue 桥接音频帧与 AsyncIterator[ASRResult]。
"""

import asyncio
import logging
from typing import AsyncIterator

from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

from .base import ASRProvider
from .types import ASRConfig, ASRResult

logger = logging.getLogger(__name__)


class DeepgramProvider(ASRProvider):
    """Deepgram 流式语音识别提供者。

    每个客户端会话创建一个实例，
    通过 WebSocket 推送音频帧到 Deepgram Live API，
    异步产出 ASRResult。
    """

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._dg_ws = None  # ListenWebSocketClient

    async def stream_transcribe(
        self,
        audio_queue: asyncio.Queue[bytes | None],
        config: ASRConfig,
    ) -> AsyncIterator[ASRResult]:
        """建立 Deepgram WebSocket，消费音频帧，流式产出结果。"""

        result_queue: asyncio.Queue[ASRResult | None] = asyncio.Queue()
        open_event = asyncio.Event()

        # ── 初始化 Deepgram 客户端 ──────────────────────────
        deepgram = DeepgramClient(self._api_key)
        dg_ws = deepgram.listen.websocket()
        self._dg_ws = dg_ws

        # ── 回调定义 (Deepgram SDK v3 的回调签名不含 self) ──
        def on_open(connection, open_result, **kwargs):
            logger.info("Deepgram connection opened")
            open_event.set()

        def on_result(connection, result, **kwargs):
            """将 Deepgram TranscriptResponse 转为 ASRResult。"""
            try:
                channel = result.channel
                alt = channel.alternatives[0]
                text = alt.transcript

                if not text or not text.strip():
                    return

                is_final = result.is_final
                confidence = alt.confidence if is_final else 0.5
                duration = result.duration if hasattr(result, "duration") else 0.0

                asr_result = ASRResult(
                    text=text.strip(),
                    is_final=is_final,
                    confidence=confidence,
                    duration=duration,
                )
                result_queue.put_nowait(asr_result)

                logger.debug(
                    "Deepgram: final=%s conf=%.2f text=%s",
                    is_final, confidence, text[:60],
                )
            except Exception:
                logger.exception("Error processing Deepgram result")

        def on_error(connection, error, **kwargs):
            logger.error("Deepgram error: %s", error)
            result_queue.put_nowait(None)

        def on_close(connection, close_code, **kwargs):
            logger.info("Deepgram connection closed (code=%s)", close_code)
            result_queue.put_nowait(None)

        # ── 注册回调 ────────────────────────────────────────
        dg_ws.on(LiveTranscriptionEvents.Open, on_open)
        dg_ws.on(LiveTranscriptionEvents.Transcript, on_result)
        dg_ws.on(LiveTranscriptionEvents.Error, on_error)
        dg_ws.on(LiveTranscriptionEvents.Close, on_close)

        # ── 配置选项 ────────────────────────────────────────
        options = LiveOptions(
            model=config.model,
            language=config.language,
            sample_rate=config.sample_rate,
            encoding=config.encoding,
            channels=config.channels,
            interim_results=config.interim_results,
            punctuate=config.punctuate,
            smart_format=config.smart_format,
        )

        # ── 启动连接 ────────────────────────────────────────
        if not dg_ws.start(options):
            logger.error("Failed to start Deepgram WebSocket")
            return

        # 等待连接就绪 (最多 10 秒)
        try:
            await asyncio.wait_for(open_event.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error("Deepgram connection timed out")
            return

        # ── 音频转发协程 ────────────────────────────────────
        async def forward_audio():
            try:
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        break
                    dg_ws.send(chunk)
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception("Audio forwarding error")
            finally:
                try:
                    dg_ws.finish()
                except Exception:
                    pass

        forward_task = asyncio.create_task(forward_audio())

        # ── 产出结果 ────────────────────────────────────────
        try:
            while True:
                result = await result_queue.get()
                if result is None:
                    break
                yield result
        finally:
            forward_task.cancel()
            try:
                await forward_task
            except asyncio.CancelledError:
                pass

    async def close(self) -> None:
        """释放 Deepgram WebSocket 连接。"""
        if self._dg_ws:
            try:
                self._dg_ws.finish()
            except Exception:
                pass
            self._dg_ws = None
