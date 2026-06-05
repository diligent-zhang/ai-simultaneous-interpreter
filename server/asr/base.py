"""ASR 提供者抽象接口。"""

import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator

from .types import ASRConfig, ASRResult


class ASRProvider(ABC):
    """流式语音识别抽象基类。

    每个客户端会话创建一个 ASR 实例，
    通过 audio_queue 接收音频帧，产出 ASRResult 流。
    """

    @abstractmethod
    async def stream_transcribe(
        self,
        audio_queue: asyncio.Queue[bytes | None],
        config: ASRConfig,
    ) -> AsyncIterator[ASRResult]:
        """从 audio_queue 消费音频帧，流式产出识别结果。

        audio_queue 中 None 值表示流结束信号。
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
        ...
