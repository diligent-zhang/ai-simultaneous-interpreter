# Slice 3: DeepSeek 翻译集成 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development

**Goal:** ASR final 结果经过滤后送 DeepSeek 流式翻译，前端展示中英双语字幕。

**Architecture:** 后端 ASR→InterimFilter→DeepSeek→SubtitleMessage，前端按 source 字段区分双语渲染。

---

### Task 1: Translator 抽象 + 类型 + Prompt

**Files:**
- Create: `server/translator/__init__.py`
- Create: `server/translator/types.py`
- Create: `server/translator/base.py`
- Create: `server/translator/prompt.py`

**All code:**

```python
# server/translator/__init__.py
"""翻译服务模块。"""
```

```python
# server/translator/types.py
"""翻译相关类型定义。"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TranslationConfig:
    model: str = "deepseek-chat"
    temperature: float = 0.3
    max_tokens: int = 512
    source_lang: str = "en"
    target_lang: str = "zh"


@dataclass
class TranslationContext:
    """翻译上下文（Slice 4 修正引擎会用到）"""
    recent_sentences: list[str] = field(default_factory=list)  # 最近3句原文
    glossary: dict[str, str] = field(default_factory=dict)     # 术语表


@dataclass
class TranslationResult:
    text: str          # 翻译后的中文文本
    is_partial: bool = False   # 是否为流式中间结果
    finish_reason: str = ""    # "stop" | "length" | ""
```

```python
# server/translator/base.py
"""翻译提供者抽象接口。"""
from abc import ABC, abstractmethod
from typing import AsyncIterator
from .types import TranslationConfig, TranslationContext, TranslationResult


class TranslationProvider(ABC):
    @abstractmethod
    async def stream_translate(
        self,
        text: str,
        context: TranslationContext,
        config: TranslationConfig,
    ) -> AsyncIterator[TranslationResult]:
        """流式翻译单句文本，产出部分/完整译文。"""
        ...

    @abstractmethod
    async def close(self) -> None:
        """释放资源。"""
        ...
```

```python
# server/translator/prompt.py
"""翻译 Prompt 模板 — 结构感知翻译。

三层策略：
1. 文本预处理过滤 → WAIT/空语义返回空
2. 结构感知翻译 → 语序调整 + 代词还原 + 多义词消歧
3. 后验证 → Slice 4 修正引擎负责
"""

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

# 翻译用户消息模板
TRANSLATION_USER_TEMPLATE = """Translate to Chinese (reply <<WAIT>> if the input is too fragmentary to translate):

{text}"""

# 带上下文的翻译模板（Slice 4 用）
TRANSLATION_WITH_CONTEXT_TEMPLATE = """Previous sentences:
{context}

Translate to Chinese (consider the context above):
{text}"""
```

---

### Task 2: DeepSeek Provider + InterimFilter + Config

**Files:**
- Create: `server/translator/deepseek_provider.py`
- Create: `server/asr/filter.py`
- Modify: `server/config.py` (add DeepSeek options)
- Modify: `server/requirements.txt` (add openai)

```python
# server/translator/deepseek_provider.py
"""DeepSeek 流式翻译实现。通过 OpenAI 兼容 API 调用。"""
import logging
from typing import AsyncIterator
from openai import AsyncOpenAI

from .base import TranslationProvider
from .types import TranslationConfig, TranslationContext, TranslationResult
from .prompt import SYSTEM_PROMPT, TRANSLATION_USER_TEMPLATE

logger = logging.getLogger(__name__)


class DeepSeekProvider(TranslationProvider):
    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1"):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def stream_translate(
        self, text: str, context: TranslationContext, config: TranslationConfig
    ) -> AsyncIterator[TranslationResult]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": TRANSLATION_USER_TEMPLATE.format(text=text)},
        ]

        try:
            stream = await self._client.chat.completions.create(
                model=config.model,
                messages=messages,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                stream=True,
            )

            accumulated = ""
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    accumulated += delta.content
                    yield TranslationResult(
                        text=accumulated,
                        is_partial=True,
                    )

            # 检查 WAIT 信号
            final_text = accumulated.strip()
            if final_text == "<<WAIT>>" or not final_text:
                yield TranslationResult(text="", is_partial=False, finish_reason="wait")
            else:
                yield TranslationResult(
                    text=final_text,
                    is_partial=False,
                    finish_reason="stop",
                )

        except Exception as e:
            logger.error("DeepSeek translation error: %s", e)
            raise

    async def close(self) -> None:
        await self._client.close()
```

```python
# server/asr/filter.py
"""Interim 结果过滤器 + 句子完整性预判。

在 ASR 结果到达翻译引擎之前进行过滤，减少无效 LLM 调用。
每句话从 20+ 次 LLM 调用降至 3-5 次，成本降低约 75%。
"""
import re
import time
import logging

logger = logging.getLogger(__name__)

# 纯标点/语气词/空文本
EXCLUDE_PATTERN = re.compile(r'^(um|uh|er|hmm|\.{3,}|\s*)$', re.IGNORECASE)


class InterimFilter:
    """ASR Interim 结果过滤器。"""

    def __init__(self, min_char_delta: int = 3, min_interval_ms: int = 200):
        self.min_char_delta = min_char_delta
        self.min_interval_ms = min_interval_ms
        self._prev_text = ""
        self._last_send_time = 0.0
        self._last_final_time = 0.0

    def should_send_to_translation(self, text: str, is_final: bool) -> bool:
        """判断是否应发送给翻译引擎。"""
        now = time.time()

        # Final 结果始终处理（内部判断完整性）
        if is_final:
            self._prev_text = text
            self._last_final_time = now
            self._last_send_time = now
            return self._should_translate(text)

        # Interim 结果
        # 规则1: 排除纯语气词
        if EXCLUDE_PATTERN.match(text):
            return False

        # 规则2: 文本变化 < min_char_delta → 跳过
        if len(text) - len(self._prev_text) < self.min_char_delta:
            return False

        # 规则3: 距上次发送 < min_interval_ms → 跳过
        if (now - self._last_send_time) * 1000 < self.min_interval_ms:
            return False

        self._prev_text = text
        self._last_send_time = now
        return self._should_translate(text)

    def _should_translate(self, text: str) -> bool:
        """句子完整性预判。"""
        # 1. 句末标点结束 → 大概率完整
        if re.search(r'[.!?。！？\n]$', text):
            return True
        # 2. 包含主谓结构
        if self._has_subject_predicate(text):
            return True
        # 3. 距离上次 final 超过 3 秒 → 强制发送
        if time.time() - self._last_final_time > 3.0:
            return True
        # 4. 文本足够长（>50字符）→ 大概率有可译内容
        if len(text) > 50:
            return True
        return False

    def _has_subject_predicate(self, text: str) -> bool:
        """简单启发式：检测主谓结构。"""
        # 常见主谓模式：代词/名词 + 动词
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

    def reset(self):
        self._prev_text = ""
        self._last_send_time = 0.0
        self._last_final_time = 0.0
```

**Modify server/config.py** — after DEEPGRAM_SAMPLE_RATE, append:

```python
    # DeepSeek 详细配置
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    DEEPSEEK_TEMPERATURE: float = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.3"))
    DEEPSEEK_MAX_TOKENS: int = int(os.getenv("DEEPSEEK_MAX_TOKENS", "512"))
```

**Modify server/requirements.txt** — append `openai>=1.0.0`:

```
openai>=1.0.0
```

---

### Task 3: 改造 main.py — ASR → Filter → Translation 管线

**Files:**
- Modify: `server/main.py` (完整覆盖)

```python
"""AI 同声传译助手 — 后端入口。

Slice 3: DeepSeek 流式翻译集成。
接收音频帧 → Deepgram ASR → InterimFilter → DeepSeek 翻译 → 双语字幕。
"""

import asyncio
import json
import logging
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.messages import (
    ConfigMessage,
    PingMessage,
    PongMessage,
    StatusMessage,
    SubtitleMessage,
)
from asr.types import ASRConfig
from asr.filter import InterimFilter
from asr.deepgram_provider import DeepgramProvider
from translator.types import TranslationConfig, TranslationContext
from translator.deepseek_provider import DeepSeekProvider

logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI Simultaneous Interpreter",
    version="0.3.0",
    description="AI 同声传译助手后端服务",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.3.0"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("Client connected")

    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    asr_task: asyncio.Task | None = None
    translation_task: asyncio.Task | None = None
    # 翻译输入队列: (text, is_final)
    translation_queue: asyncio.Queue[tuple[str, bool] | None] = asyncio.Queue()

    asr_config = ASRConfig(
        language=settings.DEEPGRAM_LANGUAGE,
        model=settings.DEEPGRAM_MODEL,
        sample_rate=settings.DEEPGRAM_SAMPLE_RATE,
    )
    trans_config = TranslationConfig(
        model=settings.DEEPSEEK_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_MAX_TOKENS,
    )

    segment_counter = 0
    asr_active = bool(settings.DEEPGRAM_API_KEY)
    translation_active = bool(settings.DEEPSEEK_API_KEY)

    async def run_asr():
        """ASR 协程：消费音频帧 → 推送英文 + 入队翻译候选。"""
        nonlocal segment_counter

        if not asr_active:
            logger.warning("DEEPGRAM_API_KEY not set, falling back to echo")
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                msg = SubtitleMessage(
                    segment_id=f"echo_{segment_counter}",
                    text=f"[Echo] {len(chunk)} bytes",
                    is_final=False, source="asr", timestamp=time.time(),
                )
                segment_counter += 1
                await ws.send_json(msg.model_dump())
            return

        try:
            provider = DeepgramProvider(api_key=settings.DEEPGRAM_API_KEY)
            interim_filter = InterimFilter()

            async for result in provider.stream_transcribe(audio_queue, asr_config):
                segment_counter += 1
                seg_id = f"seg_{segment_counter:04d}"

                # 1. 推送 ASR 英文原文到前端
                asr_msg = SubtitleMessage(
                    segment_id=seg_id,
                    text=result.text,
                    is_final=result.is_final,
                    source="asr",
                    confidence=result.confidence,
                    timestamp=time.time(),
                )
                await ws.send_json(asr_msg.model_dump())

                # 2. 过滤 → 入队翻译
                if translation_active and interim_filter.should_send_to_translation(
                    result.text, result.is_final
                ):
                    translation_queue.put_nowait((result.text, result.is_final))

        except Exception as e:
            logger.exception("ASR pipeline error: %s", e)
            await ws.send_json(StatusMessage(
                asr_status="error", translation_status="idle", latency_ms=0,
            ).model_dump())

    async def run_translation():
        """翻译协程：消费翻译候选 → DeepSeek → 推送中文译文。"""
        if not translation_active:
            logger.warning("DEEPSEEK_API_KEY not set, translation disabled")
            return

        try:
            provider = DeepSeekProvider(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
            )
            context = TranslationContext()

            while True:
                item = await translation_queue.get()
                if item is None:
                    break

                text, is_final = item
                try:
                    last_sent = ""
                    async for trans_result in provider.stream_translate(
                        text, context, trans_config
                    ):
                        # 跳过 WAIT 和重复内容
                        if trans_result.finish_reason == "wait":
                            break
                        if trans_result.text == last_sent and trans_result.is_partial:
                            continue
                        last_sent = trans_result.text

                        if trans_result.text:
                            trans_msg = SubtitleMessage(
                                segment_id=f"trans_{segment_counter:04d}",
                                text=trans_result.text,
                                is_final=not trans_result.is_partial,
                                source="translation",
                                confidence=0.9,
                                timestamp=time.time(),
                            )
                            await ws.send_json(trans_msg.model_dump())

                    # 将 final 翻译加入上下文
                    if trans_result.text and trans_result.finish_reason == "stop":
                        context.recent_sentences.append(trans_result.text)
                        if len(context.recent_sentences) > 3:
                            context.recent_sentences.pop(0)

                except Exception as e:
                    logger.error("Translation error for text '%s': %s", text[:30], e)
        except Exception as e:
            logger.exception("Translation pipeline error: %s", e)

    try:
        # 发送就绪状态
        await ws.send_json(StatusMessage(
            asr_status="connected" if asr_active else "idle",
            translation_status="connected" if translation_active else "idle",
            latency_ms=0,
        ).model_dump())

        # 启动管线
        asr_task = asyncio.create_task(run_asr())
        if translation_active:
            translation_task = asyncio.create_task(run_translation())

        # 主循环
        while True:
            data = await ws.receive()

            if "bytes" in data:
                audio_queue.put_nowait(data["bytes"])

            elif "text" in data:
                msg = json.loads(data["text"])
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    PingMessage.model_validate(msg)
                    await ws.send_json(PongMessage().model_dump())
                elif msg_type == "config":
                    ConfigMessage.model_validate(msg)
                    logger.info("Config received: %s", msg)
                    await ws.send_json(StatusMessage().model_dump())

    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error("Invalid message: %s", e)
        await ws.close(code=1003, reason="Invalid message format")
    except Exception:
        logger.exception("Unexpected error")
        await ws.close(code=1011, reason="Internal server error")
    finally:
        audio_queue.put_nowait(None)
        translation_queue.put_nowait(None)
        for task in [asr_task, translation_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


def main():
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=True)


if __name__ == "__main__":
    main()
```

---

### Task 4: 前端 — 消息类型 + 双语字幕

**Files:**
- Modify: `client/src/types/messages.ts`
- Modify: `client/src/components/SubtitleOverlay.tsx`
- Modify: `client/src/App.tsx`
- Modify: `client/src/components/AudioCapture.tsx`

**Step 1: Update types/messages.ts** — add bilingual entry type

After existing types, append:

```typescript
// ─── 前端内部字幕条目 ───────────────────────────────

export interface SubtitleEntry {
  id: string;
  text: string;
  timestamp: number;
  source: 'asr' | 'translation';
  isFinal: boolean;
}
```

Remove the old `SubtitleEntry` from App.tsx (it's now in types).

**Step 2: Update SubtitleOverlay.tsx** — bilingual rendering

```tsx
import { useEffect, useRef } from 'react';
import type { SubtitleEntry } from '../types/messages';

interface SubtitleOverlayProps {
  subtitles: SubtitleEntry[];
}

export default function SubtitleOverlay({ subtitles }: SubtitleOverlayProps) {
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

  // 按 ASR/翻译配对分组显示
  return (
    <div ref={containerRef} style={{
      position: 'fixed', bottom: '10%', left: '50%', transform: 'translateX(-50%)',
      maxWidth: '80%', maxHeight: '40vh', overflowY: 'auto',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
      pointerEvents: 'none',
    }}>
      {subtitles.slice(-8).map((entry) => (
        <div key={entry.id} style={{
          background: 'rgba(0,0,0,0.75)', borderRadius: 8,
          padding: entry.source === 'translation' ? '10px 20px' : '4px 20px',
          animation: 'fadeIn 0.3s ease-out',
          maxWidth: '100%', textAlign: 'center',
        }}>
          {entry.source === 'asr' ? (
            <div style={{
              color: 'rgba(255,255,255,0.6)', fontSize: 14, lineHeight: 1.4,
              fontStyle: entry.isFinal ? 'normal' : 'italic',
            }}>
              {entry.text}
            </div>
          ) : (
            <div style={{
              color: '#fff', fontSize: 22, fontWeight: 600, lineHeight: 1.5,
              wordBreak: 'break-word',
            }}>
              {entry.text}
            </div>
          )}
        </div>
      ))}
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
```

**Step 3: Update App.tsx** — subtitle state from WS messages

```tsx
import { useState, useCallback, useEffect } from 'react';
import AudioCapture from './components/AudioCapture';
import SubtitleOverlay from './components/SubtitleOverlay';
import { onMessage } from './services/websocket';
import type { ServerMessage, SubtitleMessage, SubscriptionEntry } from './types/messages';
import './App.css';

const MAX_SUBTITLES = 20;

function App() {
  const [subtitles, setSubtitles] = useState<SubscriptionEntry[]>([]);
  const [wsStatus, setWsStatus] = useState<string>('disconnected');
  const [isCapturing, setIsCapturing] = useState(false);

  useEffect(() => {
    const unsub = onMessage((msg: ServerMessage) => {
      if (msg.type === 'subtitle') {
        const sub = msg as SubtitleMessage;
        setSubtitles((prev) => {
          const next = [...prev, {
            id: sub.segment_id + '_' + Date.now(),
            text: sub.text,
            timestamp: sub.timestamp,
            source: sub.source,
            isFinal: sub.is_final,
          }];
          return next.slice(-MAX_SUBTITLES);
        });
      }
    });
    return unsub;
  }, []);

  const handleMessage = useCallback((_text: string) => {
    // Slice 3: subtitles come from WS SubtitleMessage, not echo
  }, []);

  return (
    <div className="app">
      <AudioCapture
        wsStatus={wsStatus}
        setWsStatus={setWsStatus}
        isCapturing={isCapturing}
        setIsCapturing={setIsCapturing}
        onMessage={handleMessage}
      />
      <SubtitleOverlay subtitles={subtitles} />
    </div>
  );
}

export default App;
```

Note: The `SubtitleEntry` type is now imported from `types/messages`. App.tsx no longer defines it locally. Fix the import.

**Step 4: Update AudioCapture.tsx** — listen for subtitle messages

The `handleServerMessage` callback should also handle `subtitle` type messages. Replace the callback with:

```tsx
  const handleServerMessage = useCallback(
    (msg: ServerMessage) => {
      if (msg.type === 'subtitle') {
        const sub = msg as SubtitleMessage;
        onMessage(sub.source === 'translation' ? sub.text : `[EN] ${sub.text}`);
      }
    },
    [onMessage]
  );
```

---

### Task 5: 安装依赖 + 验证

- [ ] `cd server && pip install openai`
- [ ] `cd server && python -c "from translator.deepseek_provider import DeepSeekProvider; from asr.filter import InterimFilter; print('OK')"`
- [ ] `cd server && timeout 5 python main.py 2>&1` — 确认无 import 错误
- [ ] `cd client && npx tsc --noEmit` — 确认 TypeScript 零错误
- [ ] Commit

---

### 自检

- [x] 后端 5 新增文件 + 3 修改
- [x] 前端 4 修改
- [x] ASR interim → 前端英文草稿；final → filter → DeepSeek → 中文译文
- [x] 无 API Key 时优雅降级
- [x] 前后端 SubtitleMessage source 字段区分 asr/translation
