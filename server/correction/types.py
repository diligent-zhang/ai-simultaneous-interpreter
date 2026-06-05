"""修正事件类型定义。"""
from dataclasses import dataclass
from enum import Enum


class CorrectionReason(str, Enum):
    TERM_INCONSISTENCY = "term_inconsistency"
    PRONOUN_RESOLUTION = "pronoun_resolution"
    SEMANTIC_COHERENCE = "semantic_coherence"
    CONTEXTUAL_REFINEMENT = "contextual_refinement"


@dataclass
class CorrectionEvent:
    segment_id: str
    old_text: str
    new_text: str
    reason: CorrectionReason
    confidence: float
