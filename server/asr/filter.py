"""Interim 结果过滤器 + 句子完整性预判。"""
import re
import time
import logging

logger = logging.getLogger(__name__)

EXCLUDE_PATTERN = re.compile(r'^(um|uh|er|hmm|\.{3,}|\s*)$', re.IGNORECASE)


class InterimFilter:
    """ASR Interim 结果过滤器。"""

    def __init__(self, min_char_delta: int = 2, min_interval_ms: int = 150,
                 force_send_chars: int = 20, force_send_timeout_ms: int = 1500):
        self.min_char_delta = min_char_delta
        self.min_interval_ms = min_interval_ms
        self.force_send_chars = force_send_chars
        self.force_send_timeout_ms = force_send_timeout_ms / 1000.0
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
        """判断当前文本是否应发送翻译。

        激进策略：检测到最小语义单元即发送，降低延迟。
        """
        # 1. 句末标点 → 完整句，必发
        if re.search(r'[.!?。！？\n]$', text):
            return True
        # 2. 包含主谓结构 → 可翻译片段
        if self._has_subject_predicate(text):
            return True
        # 3. 检测名词+动词模式（如 "the model uses", "AI is"）
        if self._has_noun_verb(text):
            return True
        # 4. 超时强制发送（1.5秒无 final）
        if time.time() - self._last_final_time > self.force_send_timeout_ms:
            return True
        # 5. 超过最小字符阈值 → 足够长即可尝试翻译
        if len(text) >= self.force_send_chars:
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

    def _has_noun_verb(self, text: str) -> bool:
        """检测名词+动词模式：更宽松的语义完整性判断。"""
        patterns = [
            # 冠词/代词 + 名词 + 动词
            r'\b(the|a|an|this|that|our|my|your|his|her|its)\s+\w{2,}\s+\w+(s|ed|ing)?\b',
            # 名词 + is/are/was/were + ...
            r'\b\w{3,}\s+(is|are|was|were|has|have|will|can|could|would|should)\b',
            # 从句引导词 (that/which/who/when/if/because) → 复合句片段
            r'\b(that|which|who|when|if|because|although|while|since)\s+\w{3,}\s+\w+',
            # 动词短语: "talking about", "working on", "looking at"
            r'\b\w+(ing|ed)\s+(about|on|at|with|for|from|into|through)\b',
            # and/or/but 连接两个以上内容 → 可能是复合语义片段
            r'\b\w{3,}\s+(and|or|but)\s+\w{3,}\b',
        ]
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return True
        return False

    def reset(self):
        self._prev_text = ""
        self._last_send_time = 0.0
        self._last_final_time = 0.0
