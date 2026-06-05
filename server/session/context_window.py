"""层级化上下文窗口 (设计文档 4.4 节)。"""
import time
from collections import OrderedDict
from dataclasses import dataclass, field


@dataclass
class ContextWindow:
    """三层上下文窗口 (~1300 tokens)。"""

    # Layer 1: 关键术语表 (全会话, ~500 tokens, LRU 淘汰)
    glossary: OrderedDict[str, str] = field(default_factory=OrderedDict)
    _max_glossary: int = 50

    # Layer 2: 话题摘要 (最近5分钟, ~500 tokens)
    topic_summary: str = ""
    _last_summary_time: float = 0.0
    _summary_interval: float = 120.0  # 每2分钟更新

    # Layer 3: 最近原文 verbatim (最近3句, ~300 tokens)
    recent_originals: list[str] = field(default_factory=list)
    _max_originals: int = 3
    recent_translations: list[str] = field(default_factory=list)

    def add_sentence(self, original: str, translation: str):
        """添加一对原文+译文到 Layer 3。"""
        self.recent_originals.append(original)
        self.recent_translations.append(translation)
        if len(self.recent_originals) > self._max_originals:
            self.recent_originals.pop(0)
        if len(self.recent_translations) > self._max_originals:
            self.recent_translations.pop(0)

    def add_term(self, en_term: str, zh_term: str):
        """添加术语到 Layer 1（LRU 淘汰）。"""
        if en_term in self.glossary:
            self.glossary.move_to_end(en_term)
        else:
            self.glossary[en_term] = zh_term
            if len(self.glossary) > self._max_glossary:
                self.glossary.popitem(last=False)

    def get_context_for_prompt(self) -> str:
        """组装上下文，用于 LLM 重译 prompt。"""
        parts = []
        if self.topic_summary:
            parts.append(f"话题背景: {self.topic_summary}")
        if self.glossary:
            terms = ", ".join(
                f"{k}→{v}" for k, v in list(self.glossary.items())[-10:]
            )
            parts.append(f"术语表: {terms}")
        if self.recent_originals:
            recent = "\n".join(
                f"原文: {o}\n译文: {t}"
                for o, t in zip(self.recent_originals, self.recent_translations)
            )
            parts.append(f"最近上下文:\n{recent}")
        return "\n\n".join(parts)

    def needs_summary_update(self) -> bool:
        """是否需要更新 Layer 2 摘要。"""
        return time.time() - self._last_summary_time > self._summary_interval

    def update_summary(self, summary: str):
        """更新 Layer 2。"""
        self.topic_summary = summary
        self._last_summary_time = time.time()
