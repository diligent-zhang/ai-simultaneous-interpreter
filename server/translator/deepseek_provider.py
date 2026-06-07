"""DeepSeek 流式翻译实现。通过 OpenAI 兼容 API 调用。"""
import logging
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI

from .base import TranslationProvider
from .types import TranslationConfig, TranslationContext, TranslationResult
from .prompt import SYSTEM_PROMPT, build_user_message

logger = logging.getLogger(__name__)


class DeepSeekProvider(TranslationProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com/v1",
        retriever: Optional[object] = None,
    ):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._retriever = retriever

    async def stream_translate(
        self,
        text: str,
        context: TranslationContext,
        config: TranslationConfig,
        session_glossary=None,
    ) -> AsyncIterator[TranslationResult]:
        # Pre-translation: retrieve glossary terms from RAG + session
        glossary = ""
        if self._retriever:
            try:
                from .tools import enrich_context
                glossary = await enrich_context(
                    text, self._retriever, session_glossary
                )
            except Exception:
                logger.debug("Glossary enrichment failed, translating without RAG")

        # Build user message with optional glossary injection
        user_message = build_user_message(text, glossary)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
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
            last_yielded = ""  # Track last yielded text for throttling
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    accumulated += delta.content

                    # 节流：中文增量 < 2 字 → 跳过（消除逐字抖动）
                    # 英文增量 < 4 chars → 跳过
                    increment = len(accumulated) - len(last_yielded)
                    has_chinese = any('一' <= c <= '鿿' for c in accumulated)
                    min_increment = 2 if has_chinese else 4
                    if increment < min_increment:
                        continue

                    last_yielded = accumulated
                    yield TranslationResult(
                        text=accumulated,
                        is_partial=True,
                    )

            final_text = accumulated.strip()
            if not final_text:
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
