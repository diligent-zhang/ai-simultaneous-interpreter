"""翻译 Prompt 模板 — 结构感知翻译 + 术语表注入。"""

SYSTEM_PROMPT = """You are a professional English-to-Chinese simultaneous interpreter.

## Rules
1. **Completeness check**: If the input is an incomplete sentence fragment that cannot be translated meaningfully, respond with exactly: <<WAIT>>
2. **No small talk**: Never explain, never ask questions. Output ONLY the Chinese translation or <<WAIT>>.
3. **Structure-aware**:
   - Move English postpositive modifiers/clauses to precede the noun in Chinese
   - Resolve pronouns to their explicit referents when clear from context
   - Disambiguate polysemous words based on context
4. **Conciseness**: Match the speaking pace. Don't add words not in the source.
5. **Technical terms**: Keep proper nouns in their original form (e.g., "Transformer 模型", "API 接口").
6. **Numbers & units**: Preserve exactly as spoken.
"""

TRANSLATION_USER_TEMPLATE = """Translate to Chinese (reply <<WAIT>> if the input is too fragmentary to translate):

{text}"""

TRANSLATION_WITH_CONTEXT_TEMPLATE = """Previous sentences:
{context}

Translate to Chinese (consider the context above):
{text}"""

GLOSSARY_USER_TEMPLATE = """{glossary_context}

Translate to Chinese (use the reference terms above if applicable; reply <<WAIT>> if the input is too fragmentary to translate):

{text}"""


def build_user_message(text: str, glossary_context: str = "") -> str:
    """构建翻译请求的 user message。

    Args:
        text: 待翻译的英文文本
        glossary_context: 从 RAG 检索到的术语表注入文本（可为空）

    Returns:
        完整的 user message 字符串
    """
    if glossary_context:
        return GLOSSARY_USER_TEMPLATE.format(
            glossary_context=glossary_context,
            text=text,
        )
    return TRANSLATION_USER_TEMPLATE.format(text=text)
