"""译前检索 + 上下文构建工具。

在翻译前从 RAG 知识库检索相关术语，构建术语表注入文本。
"""
import re
import logging

logger = logging.getLogger(__name__)

_TERM_CANDIDATE_PATTERNS = [
    re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b'),
    re.compile(r'(?<=[^\w.?!]\s)([A-Z][a-z]{2,})\b'),
    re.compile(
        r'\b((?:[a-z]+\s)?(?:learning|network|model|system|data|code|test|'
        r'search|database|server|client|cloud|security|protocol|algorithm|'
        r'function|object|class|method|variable)\w*)\b',
        re.IGNORECASE,
    ),
]

_STOP_TERMS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "been",
    "were", "they", "their", "them", "about", "which", "would", "could",
    "should", "there", "where", "after", "before", "while", "since",
    "first", "second", "last", "next", "many", "much", "some", "more",
    "most", "other", "into", "over", "under", "also", "just", "like",
    "make", "made", "well", "back", "still", "even", "only", "then",
    "now", "new", "good", "great", "same", "such", "very", "much",
    "people", "thing", "things", "time", "year", "years", "day", "days",
    "part", "parts", "way", "ways", "lot", "lots", "bit", "bits",
    "actually", "basically", "really", "probably", "maybe", "perhaps",
}


def extract_term_candidates(text: str) -> list[str]:
    """从英文源文本中提取可能的术语候选词。

    Returns:
        去重后的候选词列表，按在原文本中出现的顺序排列
    """
    candidates = []
    seen = set()

    for pattern in _TERM_CANDIDATE_PATTERNS:
        for match in pattern.finditer(text):
            term = match.group(1).strip()
            lower = term.lower()
            if lower in _STOP_TERMS:
                continue
            if len(term) < 3:
                continue
            if lower not in seen:
                seen.add(lower)
                candidates.append(term)

    return candidates[:20]


def format_glossary_context(matches: list[dict]) -> str:
    """将匹配的术语格式化为 Prompt 注入文本。

    Args:
        matches: [{"en": "LLM", "zh": "大语言模型"}, ...]

    Returns:
        "参考术语: LLM → 大语言模型; RLHF → 基于人类反馈的强化学习"
    """
    if not matches:
        return ""

    lines = []
    for m in matches:
        en = m.get("en", "")
        zh = m.get("zh", "")
        if en and zh:
            lines.append(f"{en} → {zh}")

    if not lines:
        return ""

    return "参考术语: " + "; ".join(lines)


async def enrich_context(text: str, retriever, session_glossary=None) -> str:
    """从 RAG 检索相关术语，构建术语表注入文本。

    Args:
        text: 英文源文本
        retriever: Retriever 实例（来自 rag 模块）
        session_glossary: ContextWindow 实例（会话即时学习术语）

    Returns:
        术语表注入文本，无匹配时返回空字符串
    """
    # 1. Extract term candidates from source text
    candidates = extract_term_candidates(text)

    # 2. Resolve acronyms (fast, in-memory)
    from rag.acronyms import resolve_acronyms
    acronym_matches = resolve_acronyms(text)

    # 3. RAG embedding search
    rag_matches = []
    if retriever and candidates:
        try:
            rag_matches = await retriever.search(candidates, top_k=5, threshold=0.7)
        except Exception as e:
            logger.warning("RAG search failed: %s", e)

    # 4. Session glossary search
    session_matches = []
    if session_glossary and candidates:
        try:
            for candidate in candidates:
                session_matches.extend(
                    session_glossary.search_glossary(candidate)
                )
        except Exception:
            pass

    # 5. Merge: RAG > session > acronym (priority order)
    all_matches = []
    seen_en = set()

    for m in rag_matches:
        en_lower = m["en"].lower()
        if en_lower not in seen_en:
            seen_en.add(en_lower)
            all_matches.append({"en": m["en"], "zh": m["zh"], "source": "rag"})

    for m in session_matches:
        en_lower = m["en"].lower()
        if en_lower not in seen_en:
            seen_en.add(en_lower)
            all_matches.append(m)  # Already has "source": "session"

    for m in acronym_matches:
        en_lower = m["en"].lower()
        if en_lower not in seen_en:
            seen_en.add(en_lower)
            all_matches.append({"en": m["en"], "zh": m["zh"], "source": "acronym"})

    if not all_matches:
        return ""

    logger.debug(
        "Context enriched: %d terms (rag=%d, session=%d, acronym=%d)",
        len(all_matches),
        sum(1 for m in all_matches if m.get("source") == "rag"),
        sum(1 for m in all_matches if m.get("source") == "session"),
        sum(1 for m in all_matches if m.get("source") == "acronym"),
    )
    return format_glossary_context(all_matches)
