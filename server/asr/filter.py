"""Interim 结果过滤器 + 句子完整性预判。"""
import re
import time
import logging

logger = logging.getLogger(__name__)

EXCLUDE_PATTERN = re.compile(r'^(um|uh|er|hmm|\.{3,}|\s*)$', re.IGNORECASE)


class InterimFilter:
    """ASR Interim 结果过滤器。"""

    def __init__(self, min_char_delta: int = 3, min_interval_ms: int = 200):
        self.min_char_delta = min_char_delta
        self.min_interval_ms = min_interval_ms
        self._prev_text = ""
        self._last_send_time = 0.0
        self._last_final_time = 0.0

    def should_send_to_translation(self, text: str, is_final: bool) -> bool:
        """判断是否应发送给翻译引擎。"""
        now = time.time()

        if is_final:
            self._prev_text = text
            self._last_final_time = now
            self._last_send_time = now
            return self._should_translate(text)

        if EXCLUDE_PATTERN.match(text):
            return False

        if len(text) - len(self._prev_text) < self.min_char_delta:
            return False

        if (now - self._last_send_time) * 1000 < self.min_interval_ms:
            return False

        self._prev_text = text
        self._last_send_time = now
        return self._should_translate(text)

    def _should_translate(self, text: str) -> bool:
        if re.search(r'[.!?。！？\n]$', text):
            return True
        if self._has_subject_predicate(text):
            return True
        if time.time() - self._last_final_time > 3.0:
            return True
        if len(text) > 50:
            return True
        return False

    def _has_subject_predicate(self, text: str) -> bool:
        patterns = [
            r'\b(I|we|you|he|she|it|they|this|that|these|those)\s+\w+(s|ed|ing)?\b',
            r'\b(The|A|An)\s+\w+\s+\w+(s|ed|ing)?\b',
            r'\b(There)\s+(is|are|was|were)\b',
            r'\b(It)\s+(is|was|has|will|would|could|can)\b',
        ]
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return True
        return False

    def reset(self):
        self._prev_text = ""
        self._last_send_time = 0.0
        self._last_final_time = 0.0
