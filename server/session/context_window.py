"""层级化上下文窗口 (设计文档 4.4 节)。"""
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field

# 术语提取模式：英文大写词、小写复合词
_TERM_PATTERNS = [
    re.compile(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3})\b'),
    re.compile(r'\b([a-z]{3,}(?:\s+[a-z]{3,}){0,2})\b'),
]

# 太常见不应收录为术语的词
_STOP_TERMS = {
    "the", "and", "for", "that", "this", "with", "from", "have",
    "they", "their", "them", "about", "which", "would", "could",
    "should", "there", "where", "also", "just", "like",
}


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

    def extract_terms(self, original: str, translation: str) -> int:
        """从原文+译文中提取术语对照，写入 session glossary。

        Returns:
            新增术语数量
        """
        added = 0
        for pattern in _TERM_PATTERNS:
            for match in pattern.finditer(original):
                en = match.group(1).strip().lower()
                if len(en) < 3 or en in _STOP_TERMS:
                    continue
                self.add_term(en, translation)
                added += 1
        return added

    def search_glossary(self, query: str) -> list[dict]:
        """在 session glossary 中搜索匹配的术语。

        Returns:
            [{"en": "transformer", "zh": "Transformer 模型", "source": "session"}, ...]
        """
        results = []
        query_lower = query.lower()
        for en, zh in self.glossary.items():
            if en in query_lower or query_lower in en:
                results.append({"en": en, "zh": zh, "source": "session"})
        return results[:5]

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
