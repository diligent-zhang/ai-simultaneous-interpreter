"""DeepSeek 流式翻译实现。通过 OpenAI 兼容 API 调用。"""
import logging
from typing import AsyncIterator
from openai import AsyncOpenAI

from .base import TranslationProvider
from .types import TranslationConfig, TranslationContext, TranslationResult
from .prompt import SYSTEM_PROMPT, TRANSLATION_USER_TEMPLATE

logger = logging.getLogger(__name__)


class DeepSeekProvider(TranslationProvider):
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1"):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream_translate(
        self, text: str, context: TranslationContext, config: TranslationConfig
    ) -> AsyncIterator[TranslationResult]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": TRANSLATION_USER_TEMPLATE.format(text=text)},
        ]

        try:
            stream = await self._client.chat.completions.create(
                model=config.model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=True,
            )

            accumulated = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    accumulated += delta.content
                    yield TranslationResult(
                        text=accumulated,
                        is_partial=True,
                    )

            final_text = accumulated.strip()
            if final_text == "<<WAIT>>" or not final_text:
                yield TranslationResult(text="", is_partial=False, finish_reason="wait")
            else:
                yield TranslationResult(
                    text=final_text,
                    is_partial=False,
                    finish_reason="stop",
                )

        except Exception as e:
            logger.error("DeepSeek translation error: %s", e)
            raise

    async def close(self) -> None:
        await self._client.close()
