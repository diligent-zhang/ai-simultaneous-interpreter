"""翻译提供者抽象接口。"""
from abc import ABC, abstractmethod
from typing import AsyncIterator
from .types import TranslationConfig, TranslationContext, TranslationResult


class TranslationProvider(ABC):
    @abstractmethod
    async def stream_translate(
        self,
        text: str,
        context: TranslationContext,
        config: TranslationConfig,
    ) -> AsyncIterator[TranslationResult]:
        """流式翻译单句文本，产出部分/完整译文。"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
        ...
