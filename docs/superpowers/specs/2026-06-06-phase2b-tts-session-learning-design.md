# Phase 2B: Edge TTS + 会话即时学习 — 设计文档

> 版本: v1.0 | 日期: 2026-06-06 | 状态: 待实现

---

## 一、范围概述

在 Phase 2A（RAG 知识库 + AudioWorklet 迁移）基础上，完成 Phase 2 剩余两项功能：

| 功能 | 目标 | 价值 |
|------|------|------|
| Edge TTS 切换 | 用户可选择微软 Edge TTS，音色比浏览器 SpeechSynthesis 更自然 | 体验提升 |
| 会话即时学习 | 同 session 内复用已确认术语翻译，提升术语一致性 | 翻译质量 |

**不做：** 说话者识别、跨 session 持久化、Azure TTS。

---

## 二、Edge TTS 集成

### 2.1 方案

HTTP 端点方式：后端提供流式 TTS 合成端点，前端用 `AudioContext` 独立解码播放，与浏览器 `SpeechSynthesis` 两套路径并行。

### 2.2 架构

```
翻译 final → 前端收到中文字幕
  ├── settings.ttsProvider === 'browser'
  │     → SpeechSynthesis (现有逻辑不变)
  │
  └── settings.ttsProvider === 'edge'
        → fetch('/api/tts?text=你好世界&voice=zh-CN-XiaoxiaoNeural')
        → ReadableStream → AudioContext.decodeAudioData()
        → AudioBufferSourceNode.play()
```

### 2.3 新增文件

```
server/tts/
├── __init__.py              # 模块入口
└── edge_provider.py         # Edge TTS 流式合成
```

### 2.4 Edge TTS Provider

`server/tts/edge_provider.py`：

```python
"""微软 Edge TTS 流式合成实现。使用 edge-tts 库。"""
import io
import logging
from typing import AsyncIterator

logger = logging.getLogger(__name__)

# 推荐的免费中文音色
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"   # 自然女声
ALT_VOICES = [
    "zh-CN-YunxiNeural",                   # 男声
    "zh-CN-XiaoyiNeural",                  # 轻快女声
]


async def stream_synthesize(
    text: str, voice: str = DEFAULT_VOICE, rate: str = "+10%"
) -> AsyncIterator[bytes]:
    """流式合成中文语音，产出 MP3 chunk 流。

    Args:
        text: 要合成的中文文本（长度建议 < 200 字）
        voice: 微软语音名称
        rate: 语速调整，如 "+10%" 加速 10%

    Yields:
        MP3 音频 chunk (bytes)
    """
    import edge_tts

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]
```

### 2.5 API 端点

`server/main.py` 新增：

```python
from fastapi.responses import StreamingResponse

@app.get("/api/tts")
async def tts_synthesize(
    text: str = Query(..., min_length=1, max_length=300),
    voice: str = Query(default="zh-CN-XiaoxiaoNeural"),
    rate: str = Query(default="+10%"),
):
    """流式 TTS 合成端点。返回 audio/mpeg 流。"""
    from tts.edge_provider import stream_synthesize

    return StreamingResponse(
        stream_synthesize(text, voice, rate),
        media_type="audio/mpeg",
        headers={"X-TTS-Provider": "edge"},
    )
```

### 2.6 前端修改

**`useTTS.ts` 重写：**

保持现有 API (`speak(text)`, `stop()`) 不变，内部根据 `settings.ttsProvider` 选择播放路径：

```typescript
// Edge TTS 播放路径
async function speakEdge(text: string): Promise<void> {
  const response = await fetch(
    `/api/tts?text=${encodeURIComponent(text)}&voice=${voice}&rate=${rate}`
  );
  const arrayBuffer = await response.arrayBuffer();
  const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(audioContext.destination);
  source.start();
}

// speak() 路由
function speak(text: string) {
  if (settings.ttsProvider === 'edge') {
    // 智能分块 + 队列管理 → speakEdge
  } else {
    // 现有 SpeechSynthesis 逻辑
  }
}
```

**`useSettings.ts` 修改：**

`AppSettings` 接口新增字段：

```typescript
ttsProvider: 'browser' | 'edge';  // 默认 'browser'
ttsVoice: string;                  // 默认 'zh-CN-XiaoxiaoNeural'
```

### 2.7 容错

```
Edge TTS 调用
  ├── 成功 → 播放 MP3 音频 ✅
  ├── fetch 失败（网络/服务端错误）→ 降级为 SpeechSynthesis ⚠️
  ├── 解码失败 → 降级为 SpeechSynthesis ⚠️
  └── edge-tts 库未安装 → 服务端返回 503，前端降级 ⚠️
```

### 2.8 依赖

- `edge-tts>=6.0.0` — 加入 `server/requirements.txt`
- Python 端无需额外认证或 API Key

---

## 三、会话即时学习

### 3.1 方案

复用修正引擎已有的 `ContextWindow.glossary`（50 条 LRU 术语表），在翻译确认时自动收录术语，译前检索时优先注入 session glossary 作为 Prompt 参考。

### 3.2 架构

```
翻译 final 确认
  │
  ├── ① extract_terms(原文, 译文)
  │     "transformer architecture" → "Transformer 架构"
  │     → glossary["transformer"] = "Transformer"
  │     → glossary["transformer architecture"] = "Transformer 架构"
  │
  ▼
下次翻译前
  │
  ├── ② enrich_context() 查询链:
  │     1. RAG 知识库检索 (现有逻辑)
  │     2. Session glossary 补充查
  │     3. 合并去重 → 注入 Prompt
  │
  ▼
LLM 收到: "参考术语: Transformer → Transformer (会话已确认)"
```

### 3.3 修改文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `server/session/context_window.py` | 修改 | 新增 `extract_terms()` + `search_glossary()` |
| `server/correction/engine.py` | 修改 | 翻译确认时调用 `extract_terms()` |
| `server/translator/tools.py` | 修改 | enrich_context 增加 session glossary 查询 |
| `server/translator/deepseek_provider.py` | 修改 | 接收并传递 session glossary 给 tools |
| `server/main.py` | 修改 | 创建 shared ContextWindow 传给 provider |

### 3.4 核心实现

**`context_window.py` 新增方法：**

```python
import re

# 术语提取模式：英文大写词、小写复合词
_TERM_PATTERNS = [
    re.compile(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,3})\b'),
    re.compile(r'\b([a-z]{3,}(?:\s+[a-z]{3,}){0,2})\b'),
]

# 太常见不收录的词
_STOP_TERMS = {
    "the", "and", "for", "that", "this", "with", "from", "have",
    "they", "their", "them", "about", "which", "would", "could",
    "should", "there", "where", "also", "just", "like",
}

def extract_terms(self, original: str, translation: str) -> int:
    """从原文+译文中提取术语对照，写入 glossary。"""
    added = 0
    for pattern in _TERM_PATTERNS:
        for match in pattern.finditer(original):
            en = match.group(1).strip().lower()
            if len(en) < 3 or en in _STOP_TERMS:
                continue
            # 直接收录，完整译文作为翻译参考
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

**`correction/engine.py` 修改：**

在 `process_translation()` 中，每个 final 句段确认后：

```python
# 现有：写入上下文窗口
self.context.add_sentence(original, translation)

# 新增：自动提取术语
self.context.extract_terms(original, translation)
```

**`translator/tools.py` 修改：**

`enrich_context()` 增加 session glossary 参数：

```python
async def enrich_context(
    text: str,
    retriever,
    session_glossary=None,  # 新增：ContextWindow 实例
) -> str:
    # 1-3. 现有：RAG + 缩写 检索（不变）
    ...

    # 4. 新增：Session glossary 查询
    session_matches = []
    if session_glossary:
        for candidate in candidates:
            session_matches.extend(
                session_glossary.search_glossary(candidate)
            )

    # 5. 合并：RAG > session > acronym（优先级排序）
    ...
```

### 3.5 成本分析

| 环节 | 额外计算 | 说明 |
|------|---------|------|
| `extract_terms()` | ~1ms | 正则匹配，纯本地 |
| `search_glossary()` | <1ms | O(≤50) 字典遍历 |
| Prompt 注入 | 0ms | 纯字符串拼接 |

session glossary 不做强替换（不跳过 LLM），仅作为参考注入 Prompt。这比直接替换更安全——LLM 可以判断术语是否适用当前语境。

### 3.6 容错

```
会话学习
  ├── 术语提取成功 → 写入 session glossary ✅
  ├── 提取到重复术语 → LRU 移到末尾，不新增 ✅
  ├── glossary 满 (50条) → 淘汰最旧条目 ✅
  └── extract_terms 异常 → 捕获，不影响翻译主流 ⚠️
```

---

## 四、文件变更汇总

| 文件 | 操作 | 所属功能 |
|------|------|---------|
| `server/tts/__init__.py` | 新增 | Edge TTS |
| `server/tts/edge_provider.py` | 新增 | Edge TTS |
| `server/requirements.txt` | 修改 (+ edge-tts) | Edge TTS |
| `server/main.py` | 修改 (+ GET /api/tts) | Edge TTS |
| `client/src/hooks/useTTS.ts` | 修改 (双路径) | Edge TTS |
| `client/src/hooks/useSettings.ts` | 修改 (+ ttsProvider) | Edge TTS |
| `client/src/components/SettingsPanel.tsx` | 修改 (+ TTS 切换 UI) | Edge TTS |
| `server/session/context_window.py` | 修改 (+ extract_terms, search_glossary) | 会话学习 |
| `server/correction/engine.py` | 修改 (+ 自动提取术语) | 会话学习 |
| `server/translator/tools.py` | 修改 (+ session glossary 查询) | 会话学习 |
| `server/translator/deepseek_provider.py` | 修改 (+ session glossary 参数) | 会话学习 |
| `server/main.py` | 修改 (+ 共享 ContextWindow) | 会话学习 |

---

## 五、实现顺序

1. Edge TTS 后端（tts 模块 + API 端点）
2. Edge TTS 前端（useTTS 双路径 + 设置面板）
3. 会话即时学习（ContextWindow → CorrectionEngine → Translator 链路）
4. 测试 + 集成验证
