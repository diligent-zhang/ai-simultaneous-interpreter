"""微软 Edge TTS 流式合成实现。使用 edge-tts 库。"""
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

ALT_VOICES = [
    "zh-CN-YunxiNeural",
    "zh-CN-XiaoyiNeural",
]


async def stream_synthesize(
    text: str, voice: str = DEFAULT_VOICE, rate: str = "+10%"
) -> AsyncIterator[bytes]:
    """流式合成中文语音，产出 MP3 chunk 流。

    Args:
        text: 要合成的中文文本（建议 < 200 字）
        voice: 微软语音名称
        rate: 语速调整，如 "+10%" 加速、"-10%" 减速

    Yields:
        MP3 音频 chunk (bytes)
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]
