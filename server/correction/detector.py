"""冲突检测器 — 术语/指代/语义三维检测。"""
import re
import logging
from .types import CorrectionEvent, CorrectionReason

logger = logging.getLogger(__name__)


class ConflictDetector:
    """检测翻译中的冲突和潜在错误。"""

    def detect_term_inconsistency(
        self, text: str, glossary: dict[str, str]
    ) -> list[tuple[str, str, str]]:
        """检测术语不一致。返回: [(en_term, old_zh, correct_zh), ...]"""
        conflicts = []
        for en_term, correct_zh in glossary.items():
            if en_term.lower() in text.lower():
                pass  # 简化实现，Phase 2 用 embedding 做语义匹配
        return conflicts

    def detect_pronoun_ambiguity(self, text: str) -> bool:
        """检测指代模糊：是否有未消解的代词。"""
        ambiguous_patterns = [
            r'\b(it|this|that|these|those|they|them)\b'
        ]
        for pat in ambiguous_patterns:
            if re.search(pat, text, re.IGNORECASE):
                return True
        return False

    def detect_semantic_gap(
        self, prev_translation: str, current_translation: str
    ) -> bool:
        """检测语义断裂：前后句是否有矛盾或逻辑跳跃。"""
        if prev_translation and len(current_translation) < 3:
            return True
        return False
