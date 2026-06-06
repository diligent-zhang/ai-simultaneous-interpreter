"""RAG 术语表测试。"""
import pytest


class TestDefaultGlossary:
    def test_glossary_imports(self):
        """默认术语表应可正常导入。"""
        from rag.glossary import DEFAULT_GLOSSARY
        assert isinstance(DEFAULT_GLOSSARY, list)
        assert len(DEFAULT_GLOSSARY) > 0

    def test_glossary_structure(self):
        """每条术语应有 en, zh, domain 字段。"""
        from rag.glossary import DEFAULT_GLOSSARY
        for term in DEFAULT_GLOSSARY:
            assert "en" in term, f"Missing 'en' in {term}"
            assert "zh" in term, f"Missing 'zh' in {term}"
            assert "domain" in term, f"Missing 'domain' in {term}"
            assert len(term["en"]) > 0
            assert len(term["zh"]) > 0

    def test_glossary_minimum_size(self):
        """默认术语表应至少有 150 条。"""
        from rag.glossary import DEFAULT_GLOSSARY
        assert len(DEFAULT_GLOSSARY) >= 150

    def test_glossary_valid_domains(self):
        """domain 字段应来自预定义的域。"""
        from rag.glossary import DEFAULT_GLOSSARY
        valid_domains = {"AI", "CS", "Business", "Other"}
        for term in DEFAULT_GLOSSARY:
            assert term["domain"] in valid_domains, (
                f"Unknown domain '{term['domain']}' in term '{term['en']}'"
            )

    def test_glossary_no_duplicates(self):
        """不应有重复的英文术语。"""
        from rag.glossary import DEFAULT_GLOSSARY
        en_terms = [t["en"].lower() for t in DEFAULT_GLOSSARY]
        assert len(en_terms) == len(set(en_terms)), (
            "Duplicate English terms found in glossary"
        )


class TestAcronyms:
    def test_acronyms_import(self):
        """缩写词典应可正常导入。"""
        from rag.acronyms import ACRONYM_DICT
        assert isinstance(ACRONYM_DICT, dict)
        assert len(ACRONYM_DICT) > 0

    def test_acronyms_structure(self):
        """每条缩写应有 full form 和 Chinese translation。"""
        from rag.acronyms import ACRONYM_DICT
        for acronym, entry in ACRONYM_DICT.items():
            assert isinstance(entry, tuple), f"Expected tuple for {acronym}"
            assert len(entry) == 2, f"Expected (full, zh) for {acronym}"
            assert len(entry[0]) > 0, f"Empty full form for {acronym}"
            assert len(entry[1]) > 0, f"Empty Chinese for {acronym}"

    def test_resolve_acronyms_finds_matches(self):
        """resolve_acronyms 应在文本中找到已知缩写。"""
        from rag.acronyms import resolve_acronyms
        matches = resolve_acronyms("We use LLM and RLHF for training")
        assert len(matches) > 0
        found_terms = [m["en"] for m in matches]
        assert "LLM" in found_terms or "RLHF" in found_terms

    def test_resolve_acronyms_no_matches(self):
        """无缩写时返回空列表。"""
        from rag.acronyms import resolve_acronyms
        matches = resolve_acronyms("This is a normal sentence without acronyms")
        assert matches == []

    def test_lookup_acronym_known(self):
        """已知缩写应能查到。"""
        from rag.acronyms import lookup_acronym
        result = lookup_acronym("LLM")
        assert result is not None
        assert result["en"] == "LLM"
        assert result["zh"] == "大语言模型"

    def test_lookup_acronym_unknown(self):
        """未知缩写应返回 None。"""
        from rag.acronyms import lookup_acronym
        result = lookup_acronym("ZZZTOP")
        assert result is None

    def test_lookup_acronym_case_insensitive(self):
        """缩写查询应大小写不敏感。"""
        from rag.acronyms import lookup_acronym
        result = lookup_acronym("llm")
        assert result is not None
        assert result["en"] == "LLM"
