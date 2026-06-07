# 管道流畅度优化 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复字幕碎片化、降低翻译延迟、减少长句卡顿、实现 TTS 流畅朗读

**Architecture:** 后端优化过滤器和翻译管道（激进化过滤 + 节流输出），前端重构字幕为 update-or-append 模式 + TTS 激进流式朗读 + Edge 预取管线，消息协议新增 `replace`/`sequence` 字段

**Tech Stack:** Python FastAPI + WebSocket, React + TypeScript, Deepgram ASR, DeepSeek LLM, Edge TTS

---

### Task 1: 配置 + 消息协议升级

**Files:**
- Modify: `server/config.py:25`
- Modify: `server/models/messages.py:40-48`
- Modify: `client/src/types/messages.ts:21-29, 68-74`

- [ ] **Step 1: 增大 DeepSeek max_tokens 以支持长句**

Edit `server/config.py` line 25:

```
DEEPSEEK_MAX_TOKENS: int = int(os.getenv("DEEPSEEK_MAX_TOKENS", "512"))
```
→
```
DEEPSEEK_MAX_TOKENS: int = int(os.getenv("DEEPSEEK_MAX_TOKENS", "1024"))
```

- [ ] **Step 2: SubtitleMessage 后端新增 replace 和 sequence 字段**

Edit `server/models/messages.py`, replace the `SubtitleMessage` class (lines 40-48):

```python
class SubtitleMessage(BaseModel):
    """字幕消息：包含 ASR 识别或翻译结果。"""
    type: str = ServerMessageType.SUBTITLE
    segment_id: str = Field(description="句段唯一标识")
    text: str
    is_final: bool = False
    source: str = "asr"  # "asr" | "translation"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: float = Field(default=0.0)
    replace: bool = Field(default=False, description="前端是否替换同 segment_id 旧条目")
    sequence: int = Field(default=0, description="同 segment 内递增序号")
```

- [ ] **Step 3: 前端类型同步**

Edit `client/src/types/messages.ts`, replace `SubtitleMessage` interface (lines 21-29):

```typescript
export interface SubtitleMessage {
  type: 'subtitle';
  segment_id: string;
  text: string;
  is_final: boolean;
  source: 'asr' | 'translation';
  confidence: number;
  timestamp: number;
  replace: boolean;
  sequence: number;
}
```

Replace `SubtitleEntry` interface (lines 68-74):

```typescript
export interface SubtitleEntry {
  id: string;
  text: string;
  timestamp: number;
  source: 'asr' | 'translation';
  isFinal: boolean;
  replace: boolean;
  sequence: number;
}
```

- [ ] **Step 4: 运行现有测试确认协议兼容**

```bash
cd server && python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all 81 tests pass (Pydantic 默认值确保向后兼容)

- [ ] **Step 5: Commit**

```bash
git add server/config.py server/models/messages.py client/src/types/messages.ts
git commit -m "feat: increase max_tokens to 1024, add replace/sequence fields to subtitle protocol"
```

---

### Task 2: 过滤器激进化

**Files:**
- Modify: `server/asr/filter.py`

- [ ] **Step 1: 重写 `_should_translate` 方法**

Edit `server/asr/filter.py`, replace the `_should_translate` method (lines 44-53) and the `__init__` parameters (line 14):

First, update `__init__` to accept configurable thresholds:

```python
def __init__(self, min_char_delta: int = 2, min_interval_ms: int = 150, 
             force_send_chars: int = 20, force_send_timeout_ms: int = 1500):
    self.min_char_delta = min_char_delta
    self.min_interval_ms = min_interval_ms
    self.force_send_chars = force_send_chars
    self.force_send_timeout_ms = force_send_timeout_ms / 1000.0
    self._prev_text = ""
    self._last_send_time = 0.0
    self._last_final_time = 0.0
```

Then replace `_should_translate` (lines 44-53):

```python
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
```

- [ ] **Step 2: 新增 `_has_noun_verb` 辅助方法**

Add after `_has_subject_predicate` (after line 65):

```python
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
```

- [ ] **Step 3: 运行 ASR filter 测试**

```bash
cd server && python -m pytest tests/test_asr_filter.py -v 2>&1 | tail -20
```

Expected: tests pass. If any fail due to more aggressive behavior, update test assertions to match new thresholds.

- [ ] **Step 4: Commit**

```bash
git add server/asr/filter.py
git commit -m "feat: aggressive interim filter — lower thresholds, noun-verb detection, 1.5s timeout"
```

---

### Task 3: LLM Prompt 优化 — 移除 `<<WAIT>>` 机制

**Files:**
- Modify: `server/translator/prompt.py`

- [ ] **Step 1: 重写 SYSTEM_PROMPT**

Replace the content of `server/translator/prompt.py`:

```python
"""翻译 Prompt 模板 — 结构感知翻译 + 术语表注入。"""

SYSTEM_PROMPT = """You are a professional English-to-Chinese simultaneous interpreter.

## Rules
1. **Always translate**: Even if the input is an incomplete sentence fragment, translate what you can understand. Do NOT refuse to translate — every input has translatable content.
2. **No small talk**: Never explain, never ask questions. Output ONLY the Chinese translation.
3. **Structure-aware**:
   - Move English postpositive modifiers/clauses to precede the noun in Chinese
   - Resolve pronouns to their explicit referents when clear from context
   - Disambiguate polysemous words based on context
4. **Conciseness**: Match the speaking pace. Don't add words not in the source.
5. **Technical terms**: Keep proper nouns in their original form (e.g., "Transformer 模型", "API 接口").
6. **Numbers & units**: Preserve exactly as spoken.
7. **Streaming**: Output partial translations as you go — it's better to show a partial translation quickly than to wait for a perfect one.
"""

TRANSLATION_USER_TEMPLATE = """Translate to Chinese:

{text}"""

TRANSLATION_WITH_CONTEXT_TEMPLATE = """Previous sentences:
{context}

Translate to Chinese (consider the context above):
{text}"""

GLOSSARY_USER_TEMPLATE = """{glossary_context}

Translate to Chinese (use the reference terms above if applicable):

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
```

- [ ] **Step 2: 同步更新 DeepSeek provider 中的 `<<WAIT>>` 处理**

Edit `server/translator/deepseek_provider.py`, remove the `<<WAIT>>` handling. Replace lines 69-77:

```python
            final_text = accumulated.strip()
            if not final_text:
                yield TranslationResult(text="", is_partial=False, finish_reason="wait")
            else:
                yield TranslationResult(
                    text=final_text,
                    is_partial=False,
                    finish_reason="stop",
                )
```

- [ ] **Step 3: 运行翻译相关测试**

```bash
cd server && python -m pytest tests/test_translator_tools.py -v 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add server/translator/prompt.py server/translator/deepseek_provider.py
git commit -m "feat: remove WAIT mechanism — always translate partial input"
```

---

### Task 4: 翻译端输出节流

**Files:**
- Modify: `server/translator/deepseek_provider.py`

- [ ] **Step 1: 在流式输出中增加中文字符增量阈值**

Edit `server/translator/deepseek_provider.py`, replace the streaming loop (lines 59-77):

```python
            accumulated = ""
            last_yielded = ""  # Track last yielded text for throttling
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    accumulated += delta.content

                    # 节流：中文增量 < 2 字 → 跳过（消除逐字抖动）
                    # 英文增量 < 4 chars → 跳过
                    increment = len(accumulated) - len(last_yielded)
                    has_chinese = any('一' <= c <= '鿿' for c in accumulated)
                    min_increment = 2 if has_chinese else 4
                    if increment < min_increment:
                        continue

                    last_yielded = accumulated
                    yield TranslationResult(
                        text=accumulated,
                        is_partial=True,
                    )

            final_text = accumulated.strip()
            if not final_text:
                yield TranslationResult(text="", is_partial=False, finish_reason="wait")
            else:
                yield TranslationResult(
                    text=final_text,
                    is_partial=False,
                    finish_reason="stop",
                )
```

- [ ] **Step 2: 运行测试确认**

```bash
cd server && python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: 81 passed

- [ ] **Step 3: Commit**

```bash
git add server/translator/deepseek_provider.py
git commit -m "feat: throttle translation output — min 2 Chinese chars per yield"
```

---

### Task 5: 服务端管道 — segment_id 固定化 + replace 标记

**Files:**
- Modify: `server/main.py`

- [ ] **Step 1: 修改 run_translation 中的消息发送逻辑**

Edit `server/main.py`, replace the `run_translation` coroutine (lines 255-325):

```python
    async def run_translation():
        if not translation_active:
            logger.warning("DEEPSEEK_API_KEY not set, translation disabled")
            await ws.send_json(StatusMessage(
                asr_status="connected", translation_status="idle", latency_ms=0,
            ).model_dump())
            return

        try:
            provider = DeepSeekProvider(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
                retriever=retriever,
            )
            context = TranslationContext()
            trans_seq = 0  # 独立递增翻译计数器

            while True:
                item = await translation_queue.get()
                if item is None:
                    break

                text, is_final = item
                try:
                    trans_seq += 1
                    # 固定 segment_id：同一次翻译请求的 partial/final 共用
                    trans_seg_id = f"trans_{trans_seq:04d}"
                    partial_seq = 0

                    async for trans_result in provider.stream_translate(
                        text, context, trans_config, session_glossary=session_ctx
                    ):
                        if trans_result.finish_reason == "wait":
                            break

                        partial_seq += 1

                        if trans_result.text:
                            is_partial = trans_result.is_partial
                            trans_msg = SubtitleMessage(
                                segment_id=trans_seg_id,
                                text=trans_result.text,
                                is_final=not is_partial,
                                source="translation",
                                confidence=0.9,
                                timestamp=time.time(),
                                replace=is_partial,      # partial → 前端替换同行
                                sequence=partial_seq,
                            )
                            await ws.send_json(trans_msg.model_dump())

                    if trans_result.text and trans_result.finish_reason == "stop":
                        context.recent_sentences.append(trans_result.text)
                        if len(context.recent_sentences) > 3:
                            context.recent_sentences.pop(0)

                        if correction_engine:
                            try:
                                corr_events = correction_engine.process_translation(
                                    trans_seg_id, text, trans_result.text
                                )
                                for event in corr_events:
                                    await ws.send_json({
                                        "type": "correction",
                                        "segment_id": event.segment_id,
                                        "old_text": event.old_text,
                                        "new_text": event.new_text,
                                        "reason": event.reason.value,
                                        "confidence": event.confidence,
                                    })
                            except Exception as e:
                                logger.error("Correction engine error: %s", e)

                except Exception as e:
                    logger.error("Translation error for text '%s': %s", text[:30], e)
        except Exception as e:
            logger.exception("Translation pipeline error: %s", e)
```

- [ ] **Step 2: 同时修改 ASR 字幕的 replace 行为**

Edit `server/main.py`, in the `run_asr` coroutine, update the ASR subtitle message (near line 228-236). Change:

```python
                    asr_msg = SubtitleMessage(
                        segment_id=seg_id,
                        text=result.text,
                        is_final=result.is_final,
                        source="asr",
                        confidence=result.confidence,
                        timestamp=time.time(),
                    )
```

To:

```python
                    asr_msg = SubtitleMessage(
                        segment_id=seg_id,
                        text=result.text,
                        is_final=result.is_final,
                        source="asr",
                        confidence=result.confidence,
                        timestamp=time.time(),
                        replace=not result.is_final,  # interim → 前端替换同行
                        sequence=segment_counter,
                    )
```

- [ ] **Step 3: 运行后端测试**

```bash
cd server && python -m pytest tests/ -x -q 2>&1 | tail -5
```

Expected: all passing

- [ ] **Step 4: Commit**

```bash
git add server/main.py
git commit -m "feat: fixed segment_id for translation, replace flag for partial updates"
```

---

### Task 6: Edge TTS 预取管线 + partial 朗读支持

**Files:**
- Modify: `client/src/hooks/useTTS.ts`

- [ ] **Step 1: 重写 useTTS hook — 完整替换**

Replace the entire content of `client/src/hooks/useTTS.ts`:

```typescript
/**
 * useTTS — 双路径 TTS 朗读 Hook。
 *
 * Browser 模式: SpeechSynthesis API
 * Edge 模式: fetch /api/tts → AudioContext 解码播放（双缓冲预取管线）
 *
 * 支持激进流式朗读：partial 翻译立即朗读，增量追加。
 */
import { useRef, useCallback } from 'react';

const MAX_CHUNK = 150;
const MAX_QUEUE = 5;

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
  // 跟踪每个 segment 已朗读到的位置（用于增量朗读）
  const segmentSpokenLenRef = useRef<Map<string, number>>(new Map());

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

  /** Edge TTS path — 双缓冲预取管线，消除 chunk 间间隙 */
  const speakEdge = useCallback(
    async (chunks: string[]) => {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }
      const ctx = audioContextRef.current;

      if (chunks.length === 0) return;

      // 预取第一个 chunk
      let prefetchPromise: Promise<AudioBuffer | null> | null = fetchAndDecode(
        chunks[0], voice, ctx
      );

      for (let i = 0; i < chunks.length; i++) {
        // 等待当前 chunk 解码完成
        const audioBuffer = await prefetchPromise;
        // 立即启动下一个 chunk 的预取（管线化）
        prefetchPromise = i + 1 < chunks.length
          ? fetchAndDecode(chunks[i + 1], voice, ctx)
          : null;

        if (!audioBuffer) {
          // Edge TTS 失败 → fallback 到 Browser TTS
          speakBrowser(chunks.slice(i));
          return;
        }

        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);
        source.start();
        await new Promise<void>((resolve) => {
          source.onended = () => resolve();
        });
      }
      playingRef.current = false;
    },
    [voice, speakBrowser]
  );

  /** 从 Edge TTS API 获取并解码音频 */
  const fetchAndDecode = async (
    text: string, voiceName: string, ctx: AudioContext
  ): Promise<AudioBuffer | null> => {
    try {
      const resp = await fetch(
        `/api/tts?text=${encodeURIComponent(text)}&voice=${encodeURIComponent(voiceName)}&rate=%2B10%25`
      );
      if (!resp.ok) return null;
      const arrayBuffer = await resp.arrayBuffer();
      return await ctx.decodeAudioData(arrayBuffer);
    } catch {
      return null;
    }
  };

  /**
   * 朗读文本。如果提供了 segmentId，支持增量朗读：
   * 只朗读上次朗读位置之后的新增部分。
   */
  const speak = useCallback(
    (text: string, segmentId?: string) => {
      // 增量朗读：只读新增部分
      if (segmentId) {
        const spokenLen = segmentSpokenLenRef.current.get(segmentId) ?? 0;
        if (text.length <= spokenLen) return;  // 没有新内容
        const newPart = text.slice(spokenLen);
        segmentSpokenLenRef.current.set(segmentId, text.length);
        // 只有新增部分足够长才朗读（≥5 字）
        if (newPart.length < 5) return;
        text = newPart;
      }

      const chunks = splitAtNaturalBreaks(text, MAX_CHUNK);

      // 队列溢出：保留最后 MAX_QUEUE 个 chunk
      if (queueRef.current.length > MAX_QUEUE) {
        if (provider === 'browser') {
          window.speechSynthesis.cancel();
        }
        queueRef.current = queueRef.current.slice(-MAX_QUEUE);
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

  /** 清除指定 segment 的朗读记录（修正时用） */
  const clearSegment = useCallback((segmentId: string) => {
    segmentSpokenLenRef.current.delete(segmentId);
  }, []);

  const stop = useCallback(() => {
    if (provider === 'browser') {
      window.speechSynthesis?.cancel();
    }
    queueRef.current = [];
    playingRef.current = false;
    segmentSpokenLenRef.current.clear();
  }, [provider]);

  return { speak, stop, clearSegment };
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/hooks/useTTS.ts
git commit -m "feat: Edge TTS dual-buffer prefetch pipeline + incremental partial speak"
```

---

### Task 7: SubtitleOverlay — 字幕渲染优化

**Files:**
- Modify: `client/src/components/SubtitleOverlay.tsx`

- [ ] **Step 1: 重写 SubtitleOverlay — 完整替换**

Replace the entire content of `client/src/components/SubtitleOverlay.tsx`:

```typescript
import { useEffect, useRef } from 'react';
import type { SubtitleEntry } from '../types/messages';

interface SubtitleOverlayProps {
  subtitles: SubtitleEntry[];
  cinemaMode: boolean;
  fontSize: number;
  maxLines: number;
}

export default function SubtitleOverlay({ subtitles, cinemaMode, fontSize, maxLines }: SubtitleOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [subtitles]);

  if (subtitles.length === 0) {
    return (
      <div style={{
        position: 'fixed', bottom: '20%', left: '50%', transform: 'translateX(-50%)',
        color: 'rgba(255,255,255,0.4)', fontSize: 16, fontFamily: 'monospace',
        textAlign: 'center', pointerEvents: 'none',
      }}>
        等待音频捕获...
      </div>
    );
  }

  // 去重：同一 id 只保留最后一条（处理 replace 语义）
  const visible = dedupeSubtitles(subtitles).slice(-maxLines);

  return (
    <div ref={containerRef} style={{
      position: 'fixed', bottom: '10%', left: '50%', transform: 'translateX(-50%)',
      maxWidth: '80%', maxHeight: '45vh', overflowY: 'auto',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
      pointerEvents: 'none',
    }}>
      {visible.map((entry) => {
        const isPartialTranslation = entry.source === 'translation' && !entry.isFinal;
        return (
          <div key={entry.id} style={{
            background: cinemaMode ? 'transparent' : 'rgba(0,0,0,0.75)',
            borderRadius: 8,
            padding: entry.source === 'translation' && !cinemaMode ? '10px 20px' : cinemaMode ? '4px 20px' : '4px 20px',
            maxWidth: '100%', textAlign: 'center',
          }}>
            {entry.source === 'asr' ? (
              <div style={{
                color: 'rgba(255,255,255,0.6)', fontSize: Math.round(fontSize * 0.64),
                lineHeight: 1.4,
                fontStyle: entry.isFinal ? 'normal' : 'italic',
                opacity: entry.isFinal ? 0.8 : 0.5,
              }}>
                {entry.text}
              </div>
            ) : (
              <div style={{
                color: '#fff', fontSize, fontWeight: 600, lineHeight: 1.5,
                wordBreak: 'break-word',
                ...(cinemaMode
                  ? { textShadow: '0 1px 4px rgba(0,0,0,0.8)' }
                  : {}),
              }}>
                {entry.text}
                {isPartialTranslation && (
                  <span className="cursor-blink" style={{
                    display: 'inline-block', width: 2, height: '1em',
                    background: '#fff', marginLeft: 2, verticalAlign: 'text-bottom',
                  }} />
                )}
              </div>
            )}
          </div>
        );
      })}
      <style>{`
        @keyframes cursorBlink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .cursor-blink {
          animation: cursorBlink 0.6s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}

/**
 * 字幕去重：同 id → 保留最后一条（实现 replace 语义）
 * isFinal=true 的条目锁定，不再被后续同 id partial 替换
 */
function dedupeSubtitles(entries: SubtitleEntry[]): SubtitleEntry[] {
  const map = new Map<string, SubtitleEntry>();
  // 先记录所有 locked (final) 条目
  for (const e of entries) {
    if (e.isFinal && e.source === 'translation') {
      map.set(e.id, e);
    }
  }
  // 后遍历的会覆盖，但 locked 条目不会被非 final 覆盖
  for (const e of entries) {
    const existing = map.get(e.id);
    if (existing && existing.isFinal && existing.source === 'translation') {
      // 已锁定的 final 翻译不被 partial 或非 final 覆盖
      if (e.isFinal || e.source !== 'translation') {
        map.set(e.id, e);
      }
      // 如果是同 id 的 partial 翻译 → 跳过，不覆盖 locked final
      continue;
    }
    map.set(e.id, e);
  }
  // 按时间戳排序
  return Array.from(map.values()).sort((a, b) => a.timestamp - b.timestamp);
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/components/SubtitleOverlay.tsx
git commit -m "feat: deduplicate subtitles by id, replace partial in-place, add cursor blink"
```

---

### Task 8: App.tsx — 字幕 updateOrAppend + 激进流式 TTS

**Files:**
- Modify: `client/src/App.tsx`

- [ ] **Step 1: 重写字幕更新逻辑 + TTS 触发**

Replace the entire content of `client/src/App.tsx`:

```typescript
import { useState, useEffect, useRef } from 'react';
import AudioCapture from './components/AudioCapture';
import SubtitleOverlay from './components/SubtitleOverlay';
import SettingsPanel from './components/SettingsPanel';
import { onMessage, connect } from './services/websocket';
import { useTTS } from './hooks/useTTS';
import { useSettings } from './hooks/useSettings';
import type {
  ServerMessage,
  SubtitleMessage,
  CorrectionMessage,
  SubtitleEntry,
} from './types/messages';
import './App.css';

const MAX_SUBTITLES = 20;

function App() {
  const [subtitles, setSubtitles] = useState<SubtitleEntry[]>([]);
  const [wsStatus, setWsStatus] = useState<string>('connecting');
  const [isCapturing, setIsCapturing] = useState(false);
  const [latencyMs, setLatencyMs] = useState(0);
  const [asrProvider, setAsrProvider] = useState('Deepgram');
  const [transProvider, setTransProvider] = useState('DeepSeek');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [capturedStream, setCapturedStream] = useState<MediaStream | null>(null);
  const { settings, update } = useSettings();
  const { speak, stop, clearSegment } = useTTS({
    provider: settings.ttsProvider,
    voice: settings.ttsVoice,
  });

  // 记录每个 translation segment 已朗读到的文本位置
  const ttsSegmentTextRef = useRef<Map<string, string>>(new Map());

  // 连接预热：页面加载即建立 WS
  useEffect(() => {
    connect();
  }, []);

  useEffect(() => {
    const unsub = onMessage((msg: ServerMessage) => {
      if (msg.type === 'subtitle') {
        const sub = msg as SubtitleMessage;
        const entry: SubtitleEntry = {
          id: sub.segment_id,
          text: sub.text,
          timestamp: sub.timestamp,
          source: sub.source,
          isFinal: sub.is_final,
          replace: sub.replace,
          sequence: sub.sequence,
        };

        setSubtitles((prev) => {
          // update-or-append: replace=true 且同 id 存在 → 替换
          if (sub.replace && sub.source === 'translation') {
            const next = prev.map((s) =>
              s.id === sub.segment_id && s.source === 'translation'
                ? entry
                : s
            );
            // 如果同 id 不存在（首次 partial），追加
            if (!prev.some(s => s.id === sub.segment_id && s.source === 'translation')) {
              next.push(entry);
            }
            return next.slice(-MAX_SUBTITLES);
          }
          // ASR interim → 替换同 id 旧条目
          if (sub.replace && sub.source === 'asr') {
            const next = prev.map((s) =>
              s.id === sub.segment_id && s.source === 'asr' ? entry : s
            );
            if (!prev.some(s => s.id === sub.segment_id && s.source === 'asr')) {
              next.push(entry);
            }
            return next.slice(-MAX_SUBTITLES);
          }
          // final → 追加
          const next = [...prev, entry];
          return next.slice(-MAX_SUBTITLES);
        });

        // ─── 激进流式 TTS ─────────────────────────
        if (settings.ttsEnabled && sub.source === 'translation') {
          const prevText = ttsSegmentTextRef.current.get(sub.segment_id) ?? '';
          // 只朗读新增部分
          if (sub.text.length > prevText.length) {
            const newPart = sub.text.slice(prevText.length);
            if (newPart.length >= 5) {
              speak(newPart, sub.segment_id);
            }
          }
          ttsSegmentTextRef.current.set(sub.segment_id, sub.text);
        }
      } else if (msg.type === 'correction' && settings.correctionEnabled) {
        const corr = msg as CorrectionMessage;
        // 清除该 segment 的 TTS 记录（但已读出的声音不重读）
        clearSegment(corr.segment_id);
        // 更新字幕文字
        setSubtitles((prev) =>
          prev.map((s) =>
            s.id === corr.segment_id
              ? { ...s, text: corr.new_text, isFinal: true }
              : s
          )
        );
      } else if (msg.type === 'status') {
        const st = msg as any;
        if (st.latency_ms) setLatencyMs(st.latency_ms);
        if (st.asr_status === 'connected') setAsrProvider('Deepgram');
        else if (st.asr_status === 'error') setAsrProvider('Echo');
        if (st.translation_status === 'connected') setTransProvider('DeepSeek');
        else if (st.translation_status === 'error') setTransProvider('--');
      }
    });
    return unsub;
  }, [speak, stop, clearSegment, settings.ttsEnabled, settings.correctionEnabled]);

  const maxLines = settings.cinemaMode ? 2 : settings.maxLines;
  const fontSize = settings.cinemaMode
    ? Math.round(settings.fontSize * 0.8)
    : settings.fontSize;

  return (
    <div className={`app ${settings.cinemaMode ? 'cinema-mode' : ''}`}>
      <AudioCapture
        wsStatus={wsStatus}
        setWsStatus={setWsStatus}
        isCapturing={isCapturing}
        setIsCapturing={setIsCapturing}
        onMessage={() => {}}
        onStreamChange={setCapturedStream}
        asrProvider={asrProvider}
        transProvider={transProvider}
        latencyMs={latencyMs}
        onSettingsClick={() => setSettingsOpen(true)}
      />
      {/* 捕获的画面 */}
      {capturedStream && (
        <video
          ref={(el) => { if (el) el.srcObject = capturedStream; }}
          autoPlay
          muted
          className="captured-video"
        />
      )}

      <SubtitleOverlay
        subtitles={subtitles}
        cinemaMode={settings.cinemaMode}
        fontSize={fontSize}
        maxLines={maxLines}
      />
      <SettingsPanel
        settings={settings}
        onUpdate={update}
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  );
}

export default App;
```

- [ ] **Step 2: 确认 TypeScript 编译**

```bash
cd client && npx tsc --noEmit 2>&1 | tail -15
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add client/src/App.tsx
git commit -m "feat: update-or-append subtitle logic + aggressive streaming TTS on partial"
```

---

### Task 9: 端到端验证

**Files:**
- No new files. Manual verification.

- [ ] **Step 1: 启动后端服务**

```bash
cd server && python main.py &
```

- [ ] **Step 2: 启动前端开发服务器**

```bash
cd client && npm run dev &
```

- [ ] **Step 3: 模拟音频流测试**

```bash
cd server && python -m pytest tests/test_websocket_integration.py -v 2>&1 | tail -20
```

Expected: all integration tests pass

- [ ] **Step 4: 运行全部测试确认无回归**

```bash
cd server && python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: 81+ tests pass, no regressions

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: verify pipeline fluency optimization — all tests pass"
```
