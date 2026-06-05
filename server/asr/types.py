"""ASR 相关类型定义。"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ASRConfig:
    """ASR 服务配置。"""
    language: str = "en"
    model: str = "nova-3"  # Deepgram 最新模型
    sample_rate: int = 16000
    encoding: str = "linear16"
    channels: int = 1
    interim_results: bool = True
    punctuate: bool = True
    smart_format: bool = True


@dataclass
class ASRResult:
    """流式 ASR 识别结果。"""
    text: str
    is_final: bool = False
    confidence: float = 1.0
    duration: float = 0.0  # 音频段的秒数
    word_timestamps: Optional[list[dict]] = None
