"""Embedding 相似度检索器。"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_embedder: Optional[object] = None


def _get_embedder():
    """懒加载 embedding 模型（与 embedding/embedder.py 共用同一个模型）。"""
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedder = SentenceTransformer(
                "paraphrase-multilingual-MiniLM-L12-v2"
            )
            logger.info("RAG: embedding model loaded")
        except Exception as e:
            logger.warning("RAG: cannot load embedding model: %s", e)
            _embedder = False
    return _embedder if _embedder is not False else None


class Retriever:
    """术语检索器 — Embedding 相似度搜索 + 关键词降级。"""

    def __init__(self, collection):
        self._collection = collection
        self._embedder = _get_embedder()

    async def add_terms(self, terms: list[dict[str, str]]) -> int:
        """批量添加术语到知识库。返回成功添加的数量。"""
        if not terms:
            return 0

        ids = []
        documents = []
        metadatas = []
        embeddings = []

        for term in terms:
            en = term.get("en", "").strip()
            zh = term.get("zh", "").strip()
            if not en:
                continue

            term_id = f"term_{hash(en) & 0x7FFFFFFF:08x}"
            ids.append(term_id)
            documents.append(en)
            metadatas.append({
                "en": en,
                "zh": zh,
                "domain": term.get("domain", "Other"),
            })

            if self._embedder:
                try:
                    emb = self._embedder.encode(
                        [en], convert_to_numpy=True, show_progress_bar=False
                    )
                    embeddings.append(emb[0].tolist())
                except Exception:
                    embeddings.append(None)
            else:
                embeddings.append(None)

        valid_indices = [i for i, emb in enumerate(embeddings) if emb is not None]

        if not valid_indices:
            try:
                self._collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                )
                return len(ids)
            except Exception as e:
                logger.error("Failed to add terms: %s", e)
                return 0

        try:
            self._collection.add(
                ids=[ids[i] for i in valid_indices],
                documents=[documents[i] for i in valid_indices],
                metadatas=[metadatas[i] for i in valid_indices],
                embeddings=[embeddings[i] for i in valid_indices],
            )
            return len(valid_indices)
        except Exception as e:
            logger.error("Failed to add terms with embeddings: %s", e)
            return 0

    async def search(
        self, queries: list[str], top_k: int = 5, threshold: float = 0.7
    ) -> list[dict]:
        """搜索匹配的术语。

        Args:
            queries: 要搜索的英文术语列表
            top_k: 每词返回 top_k 个匹配
            threshold: 相似度阈值 (0-1)，低于此值的匹配被丢弃

        Returns:
            [{"en": ..., "zh": ..., "domain": ..., "score": ...}, ...]
        """
        results = []
        seen_en = set()

        for query in queries:
            try:
                matches = await self._search_single(query, top_k)
                for m in matches:
                    if m["score"] < threshold:
                        continue
                    if m["en"] in seen_en:
                        continue
                    seen_en.add(m["en"])
                    results.append(m)
            except Exception as e:
                logger.debug("Search failed for '%s': %s", query[:50], e)
                continue

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def _search_single(self, query: str, top_k: int) -> list[dict]:
        """单查询词检索。"""
        if self._embedder:
            try:
                query_emb = self._embedder.encode(
                    [query], convert_to_numpy=True, show_progress_bar=False
                )
                raw = self._collection.query(
                    query_embeddings=[query_emb[0].tolist()],
                    n_results=top_k,
                    include=["metadatas", "distances"],
                )
                return self._format_results(raw)
            except Exception as e:
                logger.debug("Embedding search failed, using keyword fallback: %s", e)

        try:
            raw = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                include=["metadatas", "distances"],
            )
            return self._format_results(raw)
        except Exception:
            return []

    def _format_results(self, raw: dict) -> list[dict]:
        """将 ChromaDB 原始结果格式化为字典列表。"""
        results = []
        if not raw.get("ids") or not raw["ids"][0]:
            return results

        ids_list = raw["ids"][0]
        metadatas_list = raw["metadatas"][0] if raw.get("metadatas") else []
        distances_list = raw["distances"][0] if raw.get("distances") else []

        for i, term_id in enumerate(ids_list):
            meta = metadatas_list[i] if i < len(metadatas_list) else {}
            distance = distances_list[i] if i < len(distances_list) else 0.0
            score = max(0.0, min(1.0, 1.0 - distance))

            results.append({
                "en": meta.get("en", ""),
                "zh": meta.get("zh", ""),
                "domain": meta.get("domain", "Other"),
                "score": round(score, 4),
            })

        return results

    async def search_by_text(self, text: str, top_k: int = 10) -> list[dict]:
        """直接根据文本搜索（用于 API 端点）。"""
        try:
            raw = self._collection.query(
                query_texts=[text],
                n_results=top_k,
                include=["metadatas", "distances"],
            )
            return self._format_results(raw)
        except Exception:
            return []
