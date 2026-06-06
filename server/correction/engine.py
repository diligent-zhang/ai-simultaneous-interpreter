"""修正引擎核心 (设计文档 4.4 节 Sidecar)。

每个翻译 final 句段进入 → 冲突检测 → 修正策略 → 修正事件
"""
import time
import logging
from dataclasses import dataclass, field

from .types import CorrectionEvent, CorrectionReason
from .detector import ConflictDetector
from embedding.embedder import should_correct
from session.context_window import ContextWindow

logger = logging.getLogger(__name__)

MAX_LLM_CORRECTIONS = 20
SILENT_WINDOW_SEC = 2.0


@dataclass
class CorrectionEngine:
    """修正引擎 Sidecar。"""

    context: ContextWindow = field(default_factory=ContextWindow)
    detector: ConflictDetector = field(default_factory=ConflictDetector)
    _correction_count: int = 0
    _segment_history: dict[str, dict] = field(default_factory=dict)

    def process_translation(
        self, segment_id: str, original: str, translation: str
    ) -> list[CorrectionEvent]:
        """处理一个 final 翻译句段，返回修正事件列表。"""
        events: list[CorrectionEvent] = []

        # 1. 写入上下文窗口
        self.context.add_sentence(original, translation)

        # 1b. 自动提取术语到 session glossary
        try:
            self.context.extract_terms(original, translation)
        except Exception:
            pass  # 不阻塞翻译主流

        self._segment_history[segment_id] = {
            "text": translation,
            "timestamp": time.time(),
            "corrected_count": 0,
        }

        # 2. 术语一致性检查
        _ = self.detector.detect_term_inconsistency(
            translation, dict(self.context.glossary)
        )

        # 3. 检查前文翻译是否需要修正
        for prev_seg_id, prev_info in list(self._segment_history.items()):
            if prev_seg_id == segment_id:
                continue
            if prev_info["corrected_count"] >= 2:
                continue

            prev_text = prev_info["text"]
            try:
                should_fix, confidence = should_correct(prev_text, translation)
            except Exception:
                continue

            if should_fix:
                event = CorrectionEvent(
                    segment_id=prev_seg_id,
                    old_text=prev_text,
                    new_text=prev_text,
                    reason=CorrectionReason.CONTEXTUAL_REFINEMENT,
                    confidence=confidence,
                )

                if (
                    confidence > 0.5
                    and self._correction_count < MAX_LLM_CORRECTIONS
                ):
                    event.reason = CorrectionReason.SEMANTIC_COHERENCE
                    event.new_text = self._llm_retranslate(prev_info, confidence)
                    self._correction_count += 1

                events.append(event)
                prev_info["corrected_count"] += 1
                prev_info["text"] = event.new_text

        # 4. 话题摘要更新
        if self.context.needs_summary_update():
            logger.info("Topic summary update triggered")
            self.context.update_summary(
                f"会话已处理 {len(self._segment_history)} 个句段"
            )

        return events

    def _llm_retranslate(self, prev_info: dict, confidence: float) -> str:
        """LLM 辅助重译 — 简化实现。完整实现在 Phase 2 接入 LLM 重译。"""
        logger.info(
            "LLM retranslation triggered (count=%d, confidence=%.2f)",
            self._correction_count,
            confidence,
        )
        return prev_info["text"]

    def get_stats(self) -> dict:
        return {
            "corrections_used": self._correction_count,
            "max_corrections": MAX_LLM_CORRECTIONS,
            "segments_tracked": len(self._segment_history),
        }
