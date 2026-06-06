# Phase 2B: Edge TTS + 会话即时学习 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Edge TTS as an alternative speech provider and enable session-level glossary term reuse for translation consistency.

**Architecture:** Edge TTS runs as a dedicated HTTP endpoint (`GET /api/tts`) streaming `audio/mpeg`; the frontend decodes via `AudioContext` in parallel to the existing `SpeechSynthesis` path. Session learning reuses the existing `ContextWindow.glossary` — each translation final auto-extracts terms, and the translator queries session glossary before LLM calls.

**Tech Stack:** `edge-tts` Python library, browser `AudioContext`, existing `ContextWindow` + `CorrectionEngine`.

---

## File Map

```
New files:
  server/tts/__init__.py                    — Module entry
  server/tts/edge_provider.py               — Edge TTS streaming synthesis

Modified files:
  server/requirements.txt                   — Add edge-tts
  server/main.py                            — Add GET /api/tts + shared ContextWindow
  client/src/hooks/useTTS.ts                — Dual-path: browser SpeechSynthesis + Edge TTS
  client/src/hooks/useSettings.ts           — Add ttsProvider, ttsVoice fields
  client/src/components/SettingsPanel.tsx   — Add TTS provider selector UI
  server/session/context_window.py          — Add extract_terms() + search_glossary()
  server/correction/engine.py               — Call extract_terms() on translation confirmation
  server/translator/tools.py                — Add session glossary to enrich_context()
  server/translator/deepseek_provider.py    — Accept and pass session_glossary
  server/tests/test_tts_edge.py             — Edge TTS unit tests
  server/tests/test_session_learning.py     — Session learning tests
```

---

### Task 1: Edge TTS Backend

**Files:**
- Create: `server/tts/__init__.py`
- Create: `server/tts/edge_provider.py`
- Modify: `server/requirements.txt`
- Modify: `server/main.py`

- [ ] **Step 1: Create TTS module init**

Write `server/tts/__init__.py`:

```python
"""TTS 语音合成模块。"""
```

- [ ] **Step 2: Create Edge TTS provider**

Write `server/tts/edge_provider.py`:

```python
"""微软 Edge TTS 流式合成实现。使用 edge-tts 库。"""
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

ALT_VOICES = [
    "zh-CN-YunxiNeural",
    "zh-CN-XiaoyiNeural",
]


async def stream_synthesize(
    text: str, voice: str = DEFAULT_VOICE, rate: str = "+10%"
) -> AsyncIterator[bytes]:
    """流式合成中文语音，产出 MP3 chunk 流。

    Args:
        text: 要合成的中文文本（建议 < 200 字）
        voice: 微软语音名称
        rate: 语速调整，如 "+10%" 加速、"-10%" 减速

    Yields:
        MP3 音频 chunk (bytes)
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]
```

- [ ] **Step 3: Add edge-tts dependency**

Edit `server/requirements.txt` — append after the last line:

```
edge-tts>=6.0.0
```

- [ ] **Step 4: Install edge-tts**

```bash
cd server && pip install edge-tts>=6.0.0
```

Expected: Package installs successfully.

- [ ] **Step 5: Add TTS API endpoint to main.py**

Add the following import to `server/main.py` (near the top with other imports):

```python
from fastapi.responses import StreamingResponse
```

Add the following endpoint before `# ─── WebSocket ───` comment in `server/main.py`:

```python
@app.get("/api/tts")
async def tts_synthesize(
    text: str = Query(..., min_length=1, max_length=300),
    voice: str = Query(default="zh-CN-XiaoxiaoNeural"),
    rate: str = Query(default="+10%"),
):
    """流式 TTS 合成端点。返回 audio/mpeg 流。"""
    try:
        from tts.edge_provider import stream_synthesize
    except ImportError:
        raise HTTPException(status_code=503, detail="TTS service unavailable")

    return StreamingResponse(
        stream_synthesize(text, voice, rate),
        media_type="audio/mpeg",
        headers={"X-TTS-Provider": "edge"},
    )
```

- [ ] **Step 6: Test the TTS endpoint**

```bash
cd server && python -c "
from fastapi.testclient import TestClient
from main import app
c = TestClient(app)
r = c.get('/api/tts?text=你好世界')
print('Status:', r.status_code)
print('Content-Type:', r.headers.get('content-type'))
print('Body size:', len(r.content), 'bytes')
"
```

Expected: `Status: 200`, `Content-Type: audio/mpeg`, `Body size: > 0 bytes`.

- [ ] **Step 7: Commit**

```bash
git add server/tts/__init__.py server/tts/edge_provider.py server/requirements.txt server/main.py
git commit -m "feat(tts): add Edge TTS provider with streaming API endpoint"
```

---

### Task 2: Edge TTS Frontend

**Files:**
- Modify: `client/src/hooks/useTTS.ts`
- Modify: `client/src/hooks/useSettings.ts`
- Modify: `client/src/components/SettingsPanel.tsx`

- [ ] **Step 1: Add TTS settings fields**

Edit `client/src/hooks/useSettings.ts` — add `ttsProvider` and `ttsVoice` to the `AppSettings` interface:

```typescript
export interface AppSettings {
  fontSize: number;
  maxLines: number;
  cinemaMode: boolean;
  ttsVolume: number;
  ttsEnabled: boolean;
  correctionEnabled: boolean;
  ttsProvider: 'browser' | 'edge';
  ttsVoice: string;
}

const DEFAULT_SETTINGS: AppSettings = {
  fontSize: 22,
  maxLines: 8,
  cinemaMode: false,
  ttsVolume: 0.8,
  ttsEnabled: true,
  correctionEnabled: true,
  ttsProvider: 'browser',
  ttsVoice: 'zh-CN-XiaoxiaoNeural',
};
```

- [ ] **Step 2: Rewrite useTTS with dual-path playback**

Replace `client/src/hooks/useTTS.ts`:

```typescript
/**
 * useTTS — 双路径 TTS 朗读 Hook。
 *
 * Browser 模式: SpeechSynthesis API（现有逻辑）
 * Edge 模式: fetch /api/tts → AudioContext 解码播放
 *
 * 两种模式共用智能分块 + 队列追进度机制。
 */
import { useRef, useCallback } from 'react';

const MAX_CHUNK = 150;
const MAX_QUEUE = 3;

interface TTSOptions {
  provider: 'browser' | 'edge';
  voice?: string;
}

export function useTTS(options?: TTSOptions) {
  const provider = options?.provider ?? 'browser';
  const voice = options?.voice ?? 'zh-CN-XiaoxiaoNeural';

  const queueRef = useRef<string[]>([]);
  const playingRef = useRef(false);
  const audioContextRef = useRef<AudioContext | null>(null);

  const splitAtNaturalBreaks = useCallback(
    (text: string, maxLen: number): string[] => {
      const chunks: string[] = [];
      let start = 0;

      while (start < text.length) {
        if (start + maxLen >= text.length) {
          chunks.push(text.slice(start));
          break;
        }

        const segment = text.slice(start, start + maxLen);
        let lastBreak = -1;
        const regex = /[，；。！？,\n]/g;
        let match: RegExpExecArray | null;

        while ((match = regex.exec(segment)) !== null) {
          lastBreak = match.index;
        }

        if (lastBreak > 0) {
          chunks.push(text.slice(start, start + lastBreak + 1));
          start = start + lastBreak + 1;
        } else {
          chunks.push(segment);
          start = start + maxLen;
        }
      }

      return chunks;
    },
    []
  );

  /** Browser SpeechSynthesis path */
  const speakBrowser = useCallback(
    (chunks: string[]) => {
      const utterances = chunks.map((chunk) => {
        const u = new SpeechSynthesisUtterance(chunk);
        u.lang = 'zh-CN';
        u.rate = 1.1;
        u.volume = 0.8;
        return u;
      });

      let idx = 0;
      const playNext = () => {
        if (idx >= utterances.length) {
          playingRef.current = false;
          return;
        }
        const u = utterances[idx++];
        u.onend = () => playNext();
        u.onerror = () => playNext();
        window.speechSynthesis.speak(u);
      };

      playingRef.current = true;
      playNext();
    },
    []
  );

  /** Edge TTS path — fetch MP3 via API, decode with AudioContext */
  const speakEdge = useCallback(
    async (chunks: string[]) => {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }
      const ctx = audioContextRef.current;

      for (const text of chunks) {
        try {
          const resp = await fetch(
            `/api/tts?text=${encodeURIComponent(text)}&voice=${encodeURIComponent(voice)}&rate=%2B10%25`
          );
          if (!resp.ok) {
            // Fallback to browser TTS on error
            speakBrowser([text]);
            continue;
          }
          const arrayBuffer = await resp.arrayBuffer();
          const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
          const source = ctx.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(ctx.destination);
          source.start();
          // Wait for this chunk to finish before playing next
          await new Promise<void>((resolve) => {
            source.onended = () => resolve();
          });
        } catch {
          // Fallback to browser TTS on error
          speakBrowser([text]);
        }
      }
      playingRef.current = false;
    },
    [voice, speakBrowser]
  );

  const speak = useCallback(
    (text: string) => {
      const chunks = splitAtNaturalBreaks(text, MAX_CHUNK);

      // Queue management: if backlog > MAX_QUEUE, skip to latest
      if (queueRef.current.length > MAX_QUEUE) {
        if (provider === 'browser') {
          window.speechSynthesis.cancel();
        }
        queueRef.current = [];
      }

      queueRef.current.push(...chunks);

      if (!playingRef.current) {
        const toPlay = [...queueRef.current];
        queueRef.current = [];
        if (provider === 'edge') {
          speakEdge(toPlay);
        } else {
          speakBrowser(toPlay);
        }
      }
    },
    [splitAtNaturalBreaks, speakBrowser, speakEdge, provider]
  );

  const stop = useCallback(() => {
    if (provider === 'browser') {
      window.speechSynthesis?.cancel();
    }
    queueRef.current = [];
    playingRef.current = false;
  }, [provider]);

  return { speak, stop };
}
```

- [ ] **Step 3: Add TTS provider selector to SettingsPanel**

Add a new row in the "语音" section of `client/src/components/SettingsPanel.tsx` — insert after the TTS 音量 row:

```tsx
<Row label="TTS 引擎">
  <select value={settings.ttsProvider}
    onChange={e => onUpdate({ ttsProvider: e.target.value as 'browser' | 'edge' })}
    style={{ background: '#333', color: '#fff', border: '1px solid #555', borderRadius: 4, padding: '2px 8px' }}>
    <option value="browser">浏览器</option>
    <option value="edge">Edge TTS</option>
  </select>
</Row>
```

- [ ] **Step 4: Update App.tsx to pass TTS settings to useTTS**

Edit `client/src/App.tsx` — change the `useTTS()` call to pass settings:

```typescript
const { speak } = useTTS({
  provider: settings.ttsProvider,
  voice: settings.ttsVoice,
});
```

- [ ] **Step 5: Build frontend to verify**

```bash
cd client && npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add client/src/hooks/useTTS.ts client/src/hooks/useSettings.ts client/src/components/SettingsPanel.tsx client/src/App.tsx
git commit -m "feat(tts): add Edge TTS dual-path playback and settings UI"
```

---

### Task 3: Session Instant Learning

**Files:**
- Modify: `server/session/context_window.py`
- Modify: `server/correction/engine.py`
- Modify: `server/translator/tools.py`
- Modify: `server/translator/deepseek_provider.py`
- Modify: `server/main.py`

- [ ] **Step 1: Add extract_terms() and search_glossary() to ContextWindow**

Edit `server/session/context_window.py` — add to the `ContextWindow` class:

```python
import re

# Term extraction patterns
_TERM_PATTERNS = [
    re.compile(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3})\b'),
    re.compile(r'\b([a-z]{3,}(?:\s+[a-z]{3,}){0,2})\b'),
]

_STOP_TERMS = {
    "the", "and", "for", "that", "this", "with", "from", "have",
    "they", "their", "them", "about", "which", "would", "could",
    "should", "there", "where", "also", "just", "like",
}
```

Add these methods to `ContextWindow` (after `add_term`):

```python
    def extract_terms(self, original: str, translation: str) -> int:
        """从原文+译文中提取术语对照，写入 glossary。

        Returns:
            新增术语数量
        """
        added = 0
        for pattern in _TERM_PATTERNS:
            for match in pattern.finditer(original):
                en = match.group(1).strip().lower()
                if len(en) < 3 or en in _STOP_TERMS:
                    continue
                self.add_term(en, translation)
                added += 1
        return added

    def search_glossary(self, query: str) -> list[dict]:
        """在 session glossary 中搜索匹配的术语。

        Returns:
            [{"en": "transformer", "zh": "Transformer 模型", "source": "session"}, ...]
        """
        results = []
        query_lower = query.lower()
        for en, zh in self.glossary.items():
            if en in query_lower or query_lower in en:
                results.append({"en": en, "zh": zh, "source": "session"})
        return results[:5]
```

- [ ] **Step 2: Call extract_terms() in CorrectionEngine**

Edit `server/correction/engine.py` — in `process_translation()`, after the existing `self.context.add_sentence(original, translation)`:

```python
        # 1. 写入上下文窗口
        self.context.add_sentence(original, translation)

        # 1b. 自动提取术语到 session glossary
        try:
            self.context.extract_terms(original, translation)
        except Exception:
            pass  # Never block the translation pipeline
```

- [ ] **Step 3: Add session glossary to enrich_context()**

Edit `server/translator/tools.py` — change the function signature and add session glossary query:

```python
async def enrich_context(
    text: str,
    retriever,
    session_glossary=None,  # ContextWindow or None
) -> str:
    """从 RAG 检索相关术语，构建术语表注入文本。"""
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

    # 4. Session glossary search (new)
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
```

- [ ] **Step 4: Pass session_glossary through DeepSeekProvider**

Edit `server/translator/deepseek_provider.py` — update `stream_translate` to accept and pass `session_glossary`:

```python
    async def stream_translate(
        self,
        text: str,
        context: TranslationContext,
        config: TranslationConfig,
        session_glossary=None,  # New: ContextWindow or None
    ) -> AsyncIterator[TranslationResult]:
        glossary = ""
        if self._retriever:
            try:
                from .tools import enrich_context
                glossary = await enrich_context(text, self._retriever, session_glossary)
            except Exception:
                logger.debug("Glossary enrichment failed, translating without RAG")
        # ... rest unchanged
```

- [ ] **Step 5: Wire shared ContextWindow in main.py**

Edit `server/main.py` — create a shared `ContextWindow` instance before the `run_asr()` and `run_translation()` functions, and pass it to the translation provider:

```python
    from session.context_window import ContextWindow

    # Shared session context for term learning
    session_ctx = ContextWindow()
```

Then update `correction_engine` creation to receive the shared context (add before `run_asr` definition):

```python
    correction_engine = CorrectionEngine(context=session_ctx) if settings.CORRECTION_ENABLED else None
```

And update the `provider.stream_translate()` call inside `run_translation()` to pass `session_glossary=session_ctx`:

```python
                    async for trans_result in provider.stream_translate(
                        text, context, trans_config, session_glossary=session_ctx
                    ):
```

- [ ] **Step 6: Run existing tests to ensure no regression**

```bash
cd server && python -m pytest tests/ -v
```

Expected: All 67 tests pass.

- [ ] **Step 7: Commit**

```bash
git add server/session/context_window.py server/correction/engine.py server/translator/tools.py server/translator/deepseek_provider.py server/main.py
git commit -m "feat(session): add session instant learning with glossary term extraction and reuse"
```

---

### Task 4: Tests

**Files:**
- Create: `server/tests/test_tts_edge.py`
- Create: `server/tests/test_session_learning.py`

- [ ] **Step 1: Write Edge TTS tests**

Write `server/tests/test_tts_edge.py`:

```python
"""Edge TTS 测试。"""
import pytest


class TestEdgeTTSProvider:
    def test_import(self):
        """模块应能正常导入。"""
        from tts.edge_provider import stream_synthesize, DEFAULT_VOICE
        assert DEFAULT_VOICE == "zh-CN-XiaoxiaoNeural"

    def test_stream_synthesize(self):
        """应能流式合成音频并产出 bytes chunk。"""
        import asyncio
        from tts.edge_provider import stream_synthesize

        async def run():
            chunks = []
            async for chunk in stream_synthesize("你好"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.get_event_loop().run_until_complete(run())
        assert len(chunks) > 0
        assert all(isinstance(c, bytes) for c in chunks)

    def test_alt_voices_available(self):
        """备用音色应可用。"""
        from tts.edge_provider import ALT_VOICES
        assert len(ALT_VOICES) >= 2


class TestTTSEndpoint:
    def test_tts_endpoint_returns_audio(self):
        """TTS 端点应返回 audio/mpeg。"""
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.get("/api/tts?text=测试")
        assert response.status_code in [200, 503]
        if response.status_code == 200:
            assert "audio" in response.headers.get("content-type", "")

    def test_tts_empty_text_rejected(self):
        """空文本应被拒绝。"""
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.get("/api/tts?text=")
        assert response.status_code == 422

    def test_tts_long_text_accepted(self):
        """300 字以内应被接受。"""
        from fastapi.testclient import TestClient
        from main import app
        client = TestClient(app)
        response = client.get("/api/tts?text=" + "测试" * 100)
        assert response.status_code in [200, 503]
```

- [ ] **Step 2: Write session learning tests**

Write `server/tests/test_session_learning.py`:

```python
"""会话即时学习测试。"""
import pytest
from session.context_window import ContextWindow


class TestContextWindowTermLearning:
    def test_extract_terms_from_simple_sentence(self):
        """应从简单句提取术语。"""
        ctx = ContextWindow()
        count = ctx.extract_terms(
            "The Transformer model achieves great results",
            "Transformer 模型取得了很好的结果",
        )
        # "Transformer" should be extracted as a term
        assert count >= 1

    def test_extract_terms_skips_stop_words(self):
        """应跳过停用词。"""
        ctx = ContextWindow()
        count = ctx.extract_terms(
            "The and for that this with",
            "这些停用词不应收录",
        )
        # All are stop words, nothing should be added
        assert "the" not in {k.lower() for k in ctx.glossary}

    def test_search_glossary_finds_match(self):
        """search_glossary 应找到匹配术语。"""
        ctx = ContextWindow()
        ctx.add_term("transformer", "Transformer 模型")
        results = ctx.search_glossary("transformer")
        assert len(results) >= 1
        assert results[0]["en"] == "transformer"
        assert results[0]["source"] == "session"

    def test_search_glossary_substring_match(self):
        """应支持子串匹配。"""
        ctx = ContextWindow()
        ctx.add_term("machine learning", "机器学习")
        results = ctx.search_glossary("learning")
        assert len(results) >= 1

    def test_search_glossary_no_match(self):
        """无匹配时应返回空列表。"""
        ctx = ContextWindow()
        ctx.add_term("transformer", "Transformer 模型")
        results = ctx.search_glossary("quantum computing")
        assert results == []

    def test_glossary_lru_eviction(self):
        """LRU 淘汰应生效（上限 50 条）。"""
        ctx = ContextWindow()
        for i in range(60):
            ctx.add_term(f"term_{i}", f"术语_{i}")
        assert len(ctx.glossary) <= 50

    def test_extract_terms_deduplication(self):
        """重复术语不应新增。"""
        ctx = ContextWindow()
        original = "Machine Learning is important"
        translation = "机器学习很重要"
        ctx.extract_terms(original, translation)
        before = len(ctx.glossary)
        ctx.extract_terms(original, translation)
        # Duplicate terms should not increase count (LRU moves them but doesn't add)
        assert len(ctx.glossary) == before

    def test_context_get_context_for_prompt(self):
        """get_context_for_prompt 应包含 session glossary。"""
        ctx = ContextWindow()
        ctx.add_term("transformer", "Transformer 模型")
        ctx.add_sentence("Hello world", "你好世界")
        prompt_context = ctx.get_context_for_prompt()
        assert "transformer" in prompt_context
        assert "Transformer 模型" in prompt_context
```

- [ ] **Step 3: Run new tests**

```bash
cd server && python -m pytest tests/test_tts_edge.py tests/test_session_learning.py -v
```

Expected: All tests pass.

- [ ] **Step 4: Run full suite**

```bash
cd server && python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add server/tests/test_tts_edge.py server/tests/test_session_learning.py
git commit -m "test: add Edge TTS and session learning tests"
```

---

### Task 5: Final Integration Verification

- [ ] **Step 1: Start the server**

```bash
cd server && timeout 5 python main.py 2>&1 || true
```

Expected: Server starts on port 8000.

- [ ] **Step 2: Test TTS endpoint via curl**

```bash
curl -s -o /dev/null -w "%{http_code} %{content_type}" "http://localhost:8000/api/tts?text=你好"
```

Expected: `200 audio/mpeg` or `503` (if edge-tts not installed).

- [ ] **Step 3: Build frontend**

```bash
cd client && npm run build
```

Expected: Build succeeds.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final integration verification for Phase 2B"
```
