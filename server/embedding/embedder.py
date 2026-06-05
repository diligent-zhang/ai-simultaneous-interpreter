"""Embedding 服务 — 用于修正置信度门控 (设计文档 4.5 节)。

计算翻译文本的语义相似度，决定是否需要触发修正。
< 0.3 → 近义词，跳过 | 0.3-0.5 → LLM 裁决 | > 0.5 → 直接修正
"""
import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

_embedder: Optional[object] = None


def _get_embedder():
    """懒加载 embedding 模型。"""
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2"
            )
            logger.info("Embedding model loaded")
        except Exception as e:
            logger.warning("Cannot load embedding model: %s, using fallback", e)
            _embedder = False
    return _embedder if _embedder is not False else None


def cosine_similarity(text1: str, text2: str) -> float:
    """计算两个文本的语义相似度 (0-1)。"""
    model = _get_embedder()
    if model is None:
        # 降级：Jaccard 字符级相似度
        set1 = set(text1)
        set2 = set(text2)
        if not set1 or not set2:
            return 0.0
        return len(set1 & set2) / len(set1 | set2)

    emb1 = model.encode([text1], convert_to_numpy=True)
    emb2 = model.encode([text2], convert_to_numpy=True)
    sim = np.dot(emb1, emb2.T)[0][0]
    return float(max(0.0, min(1.0, sim)))


def should_correct(old_text: str, new_text: str) -> tuple[bool, float]:
    """置信度门控 (设计文档 4.5 节)。

    Returns:
        (should_correct, confidence)
    """
    diff = 1.0 - cosine_similarity(old_text, new_text)

    if diff < 0.3:
        return False, diff
    if diff > 0.5:
        return True, diff
    return diff > 0.4, diff
