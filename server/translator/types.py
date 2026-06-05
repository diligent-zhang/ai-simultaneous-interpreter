"""翻译相关类型定义。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranslationConfig:
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_tokens: int = 512
    source_lang: str = "en"
    target_lang: str = "zh"


@dataclass
class TranslationContext:
    """翻译上下文（Slice 4 修正引擎会用到）"""
    recent_sentences: list[str] = field(default_factory=list)
    glossary: dict[str, str] = field(default_factory=dict)


@dataclass
class TranslationResult:
    text: str
    is_partial: bool = False
    finish_reason: str = ""
