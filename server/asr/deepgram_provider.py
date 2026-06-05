"""Deepgram 流式 ASR 实现。

使用 deepgram-sdk 的 listen_websocket() 方法，
通过 asyncio.Queue 桥接音频帧。
"""

import asyncio
import logging
from typing import AsyncIterator

from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions

from .base import ASRProvider
from .types import ASRConfig, ASRResult

logger = logging.getLogger(__name__)


class DeepgramProvider(ASRProvider):
    """Deepgram 流式语音识别提供者。"""

    def __init__(self, api_key: str):
        self._api_key = api_key
        self._connection: DeepgramClient | None = None

    async def stream_transcribe(
        self,
        audio_queue: asyncio.Queue[bytes | None],
        config: ASRConfig,
    ) -> AsyncIterator[ASRResult]:
        """建立 Deepgram WebSocket，消费音频帧，产出结果。"""
        # 创建结果队列（桥接 Deepgram 回调 → AsyncIterator）
        result_queue: asyncio.Queue[ASRResult | None] = asyncio.Queue()

        # 初始化 Deepgram 客户端
        deepgram = DeepgramClient(self._api_key)
        self._connection = deepgram

        # 配置 LiveOptions
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

        # 建立 Deepgram WebSocket 连接
        dg_ws = deepgram.listen.websocket()

        # ─── Deepgram 回调 → result_queue ───────────────────
        def on_open(*args, **kwargs):
            logger.info("Deepgram connection opened")

        def on_result(self_handler, result, **kwargs):
            """每个识别结果（interim 或 final）"""
            try:
                sentence = result.channel.alternatives[0]
                text = sentence.transcript
                if not text or not text.strip():
                    return

                is_final = result.is_final
                confidence = sentence.confidence if is_final else 0.5
                duration = result.duration if hasattr(result, 'duration') else 0.0

                asr_result = ASRResult(
                    text=text.strip(),
                    is_final=is_final,
                    confidence=confidence,
                    duration=duration,
                )
                result_queue.put_nowait(asr_result)
            except Exception as e:
                logger.error("Error processing Deepgram result: %s", e)

        def on_error(self_handler, error, **kwargs):
            logger.error("Deepgram error: %s", error)
            result_queue.put_nowait(None)  # 信号：异常终止

        def on_close(self_handler, **kwargs):
            logger.info("Deepgram connection closed")
            result_queue.put_nowait(None)  # 信号：正常结束

        # 注册回调
        dg_ws.on(LiveTranscriptionEvents.Open, on_open)
        dg_ws.on(LiveTranscriptionEvents.Transcript, on_result)
        dg_ws.on(LiveTranscriptionEvents.Error, on_error)
        dg_ws.on(LiveTranscriptionEvents.Close, on_close)

        # 启动 Deepgram 连接
        if not dg_ws.start(options):
            logger.error("Failed to start Deepgram WebSocket")
            return

        # ─── 音频转发协程 ────────────────────────────────
        async def forward_audio():
            """从 audio_queue 读取 PCM 帧，发送到 Deepgram。"""
            try:
                while True:
                    chunk = await audio_queue.get()
                    if chunk is None:
                        # 流结束信号
                        break
                    dg_ws.send(chunk)
            except Exception as e:
                logger.error("Audio forwarding error: %s", e)
            finally:
                # 发送关闭信号
                try:
                    dg_ws.finish()
                except Exception:
                    pass

        forward_task = asyncio.create_task(forward_audio())

        # ─── 产出结果 ──────────────────────────────────────
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
        """释放 Deepgram 连接资源。"""
        if self._connection:
            try:
                # Deepgram SDK 的连接在 finish() 时自动关闭
                pass
            except Exception:
                pass
            self._connection = None
