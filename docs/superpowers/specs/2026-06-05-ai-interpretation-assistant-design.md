# AI 同声传译助手 — 设计文档

> 版本: v1.1 | 日期: 2026-06-05 | 状态: 待实现

---

## 一、产品概述

### 1.1 定位

一款 Web 优先的 AI 同声传译助手，帮助用户在观看英语演讲、技术分享、国际会议和网课时，实时获取中文字幕和语音翻译，降低语言门槛。

### 1.2 核心需求

| 维度 | 选择 |
|------|------|
| 产品形态 | Web 优先，后续可扩展桌面端 |
| 音频来源 | 浏览器标签页 + 系统音频 |
| 输出形式 | 字幕 + 语音同时呈现 |
| 延迟要求 | 接近实时（1-3s），真同传体感 |
| 语言范围 | MVP：英→中，架构预留多语扩展 |
| 修正能力 | 全量上下文回溯修正（ASR 识别 + 翻译） |
| 部署方式 | MVP 云端优先，架构预留本地化 |

### 1.3 非目标 (MVP 阶段不做)

- 桌面端应用
- 多语互译（仅英译中）
- 本地部署方案
- 移动端适配

---

## 二、技术方案

### 2.1 方案选择：流式管道架构

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────┐
│ 音频捕获  │───▶│ 流式 ASR     │───▶│ 流式翻译 LLM  │───▶│ 字幕渲染  │
│(浏览器API)│    │(Deepgram)    │    │(DeepSeek 主) │    │ + TTS    │
└──────────┘    └──────────────┘    └──────────────┘    └──────────┘
                       │                    │
                       ▼                    ▼
                ┌─────────────────────────────────────┐
                │         上下文修正引擎 (Sidecar)       │
                │  · 维护滑动上下文窗口                  │
                │  · 检测前后翻译/识别冲突               │
                │  · 发出修正事件更新 UI                 │
                └─────────────────────────────────────┘
```

**各层选型：**

| 组件 | 主选 | 备用 | 说明 |
|------|------|------|------|
| ASR | Deepgram Streaming | Azure Speech | 流式+中间结果，延迟 ~300ms |
| 翻译 | DeepSeek (流式) | GPT-4o-mini | 中文翻译质量好，成本低 |
| TTS | 浏览器 SpeechSynthesis | 后续可换云端 TTS | 零成本，零传输延迟 |
| 修正引擎 | 自研 | — | 规则 + LLM 混合 |
| 后端框架 | Python FastAPI + WebSocket | — | ASR/LLM SDK 生态好 |
| 前端框架 | React + TypeScript | — | 生态成熟，组件化 |

---

## 三、整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (Browser)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 音频捕获层 │  │ 字幕渲染层 │  │ TTS 播放层 │  │  控制面板 UI  │  │
│  │ Audio    │  │ Subtitle │  │ Speech   │  │  Settings    │  │
│  │ Capture  │  │ Renderer │  │ Synthesizer│  │  Panel       │  │
│  └────┬─────┘  └────▲─────┘  └────▲─────┘  └───────────────┘  │
│       │              │             │                            │
│  ┌────▼──────────────▼─────────────▼──────────────────────────┐ │
│  │                    WebSocket 客户端                          │ │
│  │           (单一 WS 连接，双向消息，JSON + 二进制)              │ │
│  └────────────────────────┬───────────────────────────────────┘ │
└───────────────────────────┼─────────────────────────────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                           │          后端 (Server)               │
│  ┌────────────────────────▼──────────────────────────────────┐  │
│  │                   消息路由层 (Router)                       │  │
│  │         音频帧 → ASR | 翻译结果 ← LLM | 修正事件 → 前端     │  │
│  └───┬──────────────────┬──────────────────┬────────────────┘  │
│      │                  │                  │                    │
│  ┌───▼──────┐   ┌───────▼──────┐   ┌──────▼──────────────┐    │
│  │ ASR 服务  │   │  翻译服务     │   │   修正引擎           │    │
│  │ Deepgram │   │  DeepSeek    │   │   Correction        │    │
│  │ 流式识别  │   │  流式翻译     │   │   Engine            │    │
│  │ 中间结果  │   │  + FC + RAG*  │   │   上下文窗口         │    │
│  └───┬──────┘   └───────┬──────┘   │   冲突检测+回写      │    │
│      │                  │           └──────────┬──────────┘    │
│      │           ┌──────▼──────┐               │               │
│      │           │  会话状态    │◄──────────────┘               │
│      │           │  Session    │                                │
│      │           │  翻译历史    │                                │
│      │           │  上下文缓存  │                                │
│      └───────────┴─────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

### 通信协议

> 注：架构图中标注 `*` 的 FC/RAG 组件为 Phase 2 范围，MVP 不包含。

- 协议：单一 WebSocket（双向低延迟）
- 音频：二进制帧（PCM 16kHz 16bit mono），40ms/帧
- 控制/数据：JSON 消息
- 心跳：30s 间隔 ping/pong

---

## 四、核心数据流 & 修正机制

### 4.1 翻译流水线

```
时间轴 ───────────────────────────────────────────────────▶

说话者:   "Artificial intelligence...  is transforming...   every industry..."
           ─────┬─────              ───────┬───────        ──────┬──────
                │                         │                      │
ASR 中间结果:  "Artif..."(0.3s)    "AI is trans..."(1.2s)   "AI is transforming
                │                         │                  every industry"(2.1s)
                ▼                         ▼                      ▼
翻译输出:      "人工..."(0.5s)      "人工智能正在改变..."(1.5s)  "人工智能正在重塑
                                                                 每一个行业"(2.5s)
                                                          
修正触发:                                          ┌─────────────────────┐
   当后续上下文揭示 "transforming" 在此语境下      │ 修正事件:             │
   应译为"重塑"而非"改变"时 ────────────────────▶  │ 旧: 人工智能正在改变... │
                                                   │ 新: 人工智能正在重塑... │
                                                   └─────────────────────┘
```

### 4.2 客户端预处理过滤

在 ASR 结果发送到 LLM 翻译之前，浏览器端做轻量过滤，减少无效翻译调用。

**过滤规则（<0.1ms）：**

```typescript
interface InterimFilter {
  // 规则1: 文本变化 < 3 字符 → 跳过
  minCharDelta: 3,
  // 规则2: 距上次发送 < 200ms → 跳过（防止高频抖动）
  minIntervalMs: 200,
  // 规则3: 纯标点/语气词 → 跳过
  excludePattern: /^(um|uh|er|hmm|\.{2,}|\s*)$/i
}

function shouldSendToTranslation(
  text: string, 
  prevText: string, 
  timeSinceLastSend: number
): boolean {
  if (text.length - prevText.length < 3) return false;
  if (timeSinceLastSend < 200) return false;
  if (/^(um|uh|er|hmm|\.{3,}|\s*)$/i.test(text)) return false;
  return true;
}
```

**句子完整性预判（浏览器端，<0.5ms）：**

```typescript
function shouldTranslate(text: string, timeSinceLastFinal: number): boolean {
  // 1. 以句末标点结束 → 大概率完整，发送
  if (/[.!?。！？\n]$/.test(text)) return true;
  // 2. 包含完整的主谓结构 (简单启发式，正则规则)
  if (hasSubjectPredicatePattern(text)) return true;
  // 3. 距离上次 final 已超过 3 秒 → 强制发送，避免长时间空白
  if (timeSinceLastFinal > 3000) return true;
  // 4. 纯 interim 片段 → 不调用 LLM，节省成本
  return false;
}
```

**效果**：每句话从 20+ 次 LLM 调用降至 3-5 次，成本降低约 75%，延迟不受影响，且 WAIT 判断从 LLM 移到了浏览器端。

### 4.3 三层递进翻译策略

#### 第一层：智能分块（Chunking）

不做逐词翻译，也不等完整句子。在自然语义断点处翻译。

- 浏览器端先做完整性预判（见 4.2），通过后才发送 LLM
- LLM 收到后二次判断：当前输入是否构成可翻译的完整语义单元
- 不完整时返回等待信号，不强行翻译
- 减少因语序差异导致的回溯修正
- 浏览器端预判节省了大部分"WAIT"类无效 LLM 调用

#### 第二层：结构感知翻译（Structure-Aware Translation）

翻译 Prompt 内建规则：
- **断句规则**：不完整语义片段 → 等待
- **语序调整规则**：英译中主动调整（后置定语/状语 → 中文前置）
- **上下文规则**：代词还原、多义词消歧
- **修正规则**：检测到前文翻译有误时，在同一次调用中输出修正指令

#### 第三层：后验证修正（兜底）

三个修正维度：

| 维度 | 触发条件 | 处理方式 |
|------|---------|---------|
| 术语一致性 | 同一英文词前后译法不同 | 规则匹配 → 直接替换（不调 LLM，<5ms） |
| 语序结构 | 后续内容揭示前文语序需调整 | 携带完整上下文 → LLM 重译（~300ms） |
| 指代消解 | 代词指向前文未明确的概念 | LLM 判断指代 → 替换为具体名词（~200ms） |

### 4.4 修正消息协议

```json
// 翻译修正
{
  "type": "translation_correction",
  "segment_id": "seg_042",
  "old_text": "人工智能正在改变每一个行业",
  "new_text": "人工智能正在重塑每一个行业",
  "reason": "contextual_refinement",
  "confidence": 0.92
}

// 识别修正
{
  "type": "asr_correction",
  "segment_id": "seg_041",
  "old_text": "I think the model is great",
  "new_text": "I think the model is grade A",
  "reason": "acoustic_clarification",
  "confidence": 0.88
}
```

### 4.5 修正静默窗口与置信度门控

**修正静默窗口：**
- final 后 2 秒内：允许静默修正（用户不易察觉）
- final 后超过 2 秒：修正时前端不做动画（影院模式）/ 做轻动画（悬浮窗模式）
- 同一 segment 最多修正 2 次，避免反复闪烁

**修正置信度门控（避免过度修正）：**

并非所有翻译差异都需要修正。"改变"和"重塑"语义接近，强行统一的修正反而是退步。

```python
def should_correct(old: str, new: str, context: str) -> tuple[bool, float]:
    """
    通过语义差异阈值 + LLM 确认，决定是否触发修正。
    返回 (是否修正, 置信度)
    """
    # 1. 计算语义差异 (embedding cosine distance)
    old_emb = embed(old)
    new_emb = embed(new)
    similarity = cosine_similarity(old_emb, new_emb)
    diff = 1 - similarity
    
    # 2. 语义差异 < 0.3 → 近义词替换，不修正，避免闪烁
    if diff < 0.3:
        return False, 1.0 - diff
    
    # 3. 差异 0.3-0.5 → 边界情况，调用 LLM 裁决
    if diff < 0.5:
        judgment = llm.judge_correction_necessity(old, new, context)
        return judgment.is_needed, judgment.confidence
    
    # 4. 差异 > 0.5 → 明显错误，直接修正
    return True, diff
```

**门控效果：**
- 近义词替换（"改变"↔"重塑"）→ 不修正，diff ≈ 0.2
- 术语漂移（"模型"↔"模式" for "model"）→ LLM 裁决，diff ≈ 0.4
- 明显错译（"狗"↔"猫"）→ 直接修正，diff > 0.7

---

## 五、前端设计

### 5.1 组件树

```
App
├── AudioCapture          ← 音频源选择 + 捕获
│   ├── TabCapture        ← 浏览器标签页捕获 (getDisplayMedia)
│   └── SystemAudio       ← 系统音频 (后续桌面端)
│
├── InterimFilter          ← 客户端预处理 (减少 LLM 调用)
│
├── WebSocketClient       ← 后端通信 (单例)
│
├── SubtitleOverlay       ← 字幕浮层
│   ├── SubtitleLine[]    ← 多条字幕行 (滚动/淡出)
│   ├── CorrectionAnim    ← 修正动画
│   └── ConfidenceBadge   ← 置信度指示 (可选)
│
├── TTSController         ← 语音合成控制
│   ├── SpeechSynthesis   ← 浏览器 TTS API
│   ├── VoiceSelector     ← 中文音色选择
│   └── VolumeControl     ← TTS 音量独立调节
│
└── SettingsPanel         ← 控制面板 (抽屉式)
    ├── LanguageSelector  ← 源语言/目标语言
    ├── ProviderConfig    ← API Key / 服务地址配置
    ├── CorrectionToggle  ← 修正开关 + 灵敏度
    └── DisplaySettings   ← 字号/颜色/位置/行数
```

### 5.2 两种呈现模式

| | 悬浮窗模式 (默认) | 影院模式 (全屏/视频) |
|------|------|------|
| 适用场景 | 网页浏览、会议、网课 | 电影、全屏视频、演讲全屏 |
| 背景 | 半透明黑底 | 仅文字阴影描边 |
| 字号 | 正常 | 缩小 20% |
| 最大行数 | 5-8 行 | 2 行 |
| 修正动画 | 有（划掉→滑入） | 无（静默替换） |
| 状态标记 | 颜色闪烁 | 无闪烁，仅淡入 |
| 穿透点击 | 是 | 是 |
| 控制入口 | 顶部状态栏 | 右下角可收起图标 |

### 5.3 影院模式附加行为

- 字幕透明度联动视频控制条：控制条显示时字幕显示，控制条隐藏时字幕同步隐藏
- 视频暂停时字幕冻结（不新增）
- 右下角图标悬停展开最小控制条，3 秒无操作自动收起

### 5.4 TTS 行为

Chrome `SpeechSynthesis` 存在已知 bug：长文本 (>200 字) 的 utterance 会被静默截断。需要智能分块朗读。

**分块策略：**

```typescript
function speakWithChunking(text: string): void {
  const MAX_CHUNK = 150; // 字符，安全阈值
  
  // 在自然断点处分块 (逗号、分号、从句边界)
  const chunks = splitAtNaturalBreaks(text, MAX_CHUNK);
  
  for (const chunk of chunks) {
    const utterance = new SpeechSynthesisUtterance(chunk);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.1;  // 稍快 10%，匹配同传节奏
    utterance.volume = ttsVolume;
    speechQueue.push(utterance);
  }
}

function splitAtNaturalBreaks(text: string, maxLen: number): string[] {
  const breakPoints = /[，；。！？,\n]/g;
  // 在最近的断点处分割，保证每段 ≤ maxLen
  // ...
}
```

**播放行为：**
- 浏览器 `SpeechSynthesis API`，音色 `zh-CN`
- 播放队列：每个 stable 句段分块后入队
- 追进度机制：队列 >3 个句段积压 → 跳过中间句段，直接播最新
- 被修正句段不重新朗读
- 用户可独立调节 TTS 音量（与系统音量分离）

### 5.5 顶部状态栏

```
🟢 Deepgram · DeepSeek · 延迟 0.8s     ← 一切正常
🟡 Deepgram · DeepSeek⏳· 延迟 2.1s    ← 翻译慢但可用
🔴 Azure · GPT-4o-mini · 延迟 1.2s     ← 已切换备用
```

---

## 六、后端设计

### 6.1 服务结构

```
server/
├── main.py                  ← FastAPI 入口 + WebSocket 端点
├── config.py                ← 配置管理 (环境变量 + 运行时)
├── router.py                ← WebSocket 消息路由
│
├── asr/
│   ├── base.py              ← ASR 抽象接口
│   ├── deepgram_provider.py ← Deepgram 流式实现
│   ├── azure_provider.py    ← Azure Speech (备用)
│   └── types.py             ← ASR 结果类型定义
│
├── translator/
│   ├── base.py              ← 翻译抽象接口
│   ├── deepseek_provider.py ← DeepSeek 流式实现 (主)
│   ├── openai_provider.py   ← GPT-4o-mini (备)
│   ├── prompt.py            ← 翻译 Prompt 模板
│   └── types.py             ← 翻译结果类型定义
│
├── correction/
│   ├── engine.py            ← 修正引擎核心
│   ├── detector.py          ← 冲突检测 (术语/指代/语义)
│   └── types.py             ← 修正事件类型定义
│
├── embedding/
│   └── embedder.py           ← Embedding 服务 (修正置信度门控)
│
├── session/
│   ├── manager.py           ← 会话管理器
│   └── context_window.py    ← 层级化上下文窗口
│
├── rag/                     ← Phase 2
│   ├── store.py             ← 向量数据库 (Chroma)
│   ├── embedder.py          ← Embedding 服务
│   └── retriever.py         ← 检索接口
│
└── models/
    └── messages.py          ← WebSocket 消息协议定义
```

### 6.2 核心抽象接口

```python
class ASRProvider(ABC):
    """流式语音识别抽象"""
    async def stream_transcribe(
        self,
        audio_stream: AsyncIterator[bytes],
        config: ASRConfig
    ) -> AsyncIterator[ASRResult]: ...

class TranslationProvider(ABC):
    """流式翻译抽象"""
    async def stream_translate(
        self,
        text_stream: AsyncIterator[str],
        context: TranslationContext,
        config: TranslationConfig
    ) -> AsyncIterator[TranslationResult]: ...
```

### 6.3 WebSocket 消息协议

```
客户端 → 服务端:
┌──────────────────────────────────────────────────┐
│ audio_frame  │ 二进制 │ PCM 数据 (640 bytes/40ms) │
│ config       │ JSON   │ {src_lang, tgt_lang, ...}│
│ ping         │ JSON   │ 心跳                      │
└──────────────────────────────────────────────────┘

服务端 → 客户端:
┌──────────────────────────────────────────────────┐
│ subtitle     │ JSON   │ {segment_id, text,        │
│              │        │  is_final, confidence, ts}│
│ correction   │ JSON   │ {segment_id, old_text,    │
│              │        │  new_text, reason}        │
│ status       │ JSON   │ {asr_status, llm_status,  │
│              │        │  latency_ms}              │
│ pong         │ JSON   │ 心跳响应                   │
└──────────────────────────────────────────────────┘
```

### 6.4 修正引擎与层级化上下文

**层级化上下文窗口：**

FIFO 平权窗口的问题：第 1 句定义的核心术语，到第 11 句就被丢弃了。改用三层结构：

```
┌──────────────────────────────────────────────┐
│  Layer 1: 关键术语表 (全会话持续)              │
│  "transformer" → "Transformer 模型"          │
│  "RLHF" → "基于人类反馈的强化学习"            │
│  大小: ~500 tokens, 永不逐出                  │
│  管理: 新术语自动入表，有 LRU 淘汰             │
├──────────────────────────────────────────────┤
│  Layer 2: 话题摘要 (最近 5 分钟)               │
│  LLM 每 ~2 分钟自动生成一次会话摘要            │
│  大小: ~500 tokens                           │
│  作用: 提供中距离上下文，消解指代和话题漂移    │
├──────────────────────────────────────────────┤
│  Layer 3: 最近原文 verbatim (最近 3 句)        │
│  大小: ~300 tokens                           │
│  作用: 提供紧邻上下文，保证语篇连贯            │
└──────────────────────────────────────────────┘
总上下文: ~1300 tokens，远低于模型窗口，留足生成空间
```

**核心流程:**

1. 每个 final 句段进入:
   a. 原始文本追加到 Layer 3（最近原文）
   b. 提取关键术语 → Layer 1 去重入表（LRU 淘汰）
   c. 对三层上下文做冲突检测

2. 冲突检测维度:
   · 术语一致性: 同一英文词前后译法不同（Layer 1 术语表辅助判断）
   · 指代消解: 代词指向不明确，Layer 2 摘要提供中距消歧
   · 语义连贯: 前后句存在因果/转折但翻译未体现

3. 修正策略:
   · 小修正 (术语替换): 本地规则，不调用 LLM (<5ms)
   · 大修正 (指代/语序): 携带三层上下文调用 LLM 重译 (~300ms)
   · 置信度门控: semantic diff < 0.3 不修正，0.3-0.5 LLM 裁决，>0.5 直接修正
   · 成本控制: 单次会话最多 20 次 LLM 修正调用

4. 话题摘要更新:
   · LLM 每 ~2 分钟生成一次 Layer 2 摘要（异步，不阻塞主线）

5. 输出:
   · 修正事件 {type, segment_id, old_text, new_text, reason, confidence}
```

### 6.5 延迟预算

**稳态延迟（预热后）：**

| 环节 | 目标延迟 | 说明 |
|------|---------|------|
| 浏览器音频采集 | ~20ms | 40ms/帧，采集即发 |
| 客户端预处理过滤 | ~1ms | Interim 过滤 + 完整性预判 |
| 网络传输 (上行) | ~50ms | PCM 原始音频 |
| Deepgram ASR (首 interim) | ~300ms | 流式 API（连接已预热） |
| DeepSeek 翻译 (首 token) | ~500ms | 流式输出（连接已预热） |
| 网络传输 (下行) | ~50ms | 单句 JSON <1KB |
| 前端渲染 + TTS 启动 | ~50ms | 瞬时（TTS 分块预加载） |
| **稳态总计** | **~971ms** | 稳定低于 3s 目标 |

**冷启动额外延迟（无预热时首句）：**

| 环节 | 额外延迟 |
|------|---------|
| Deepgram WS 连接建立 | ~200ms |
| DeepSeek API 冷启动 | ~300ms |
| **冷启动总计** | **~1471ms** |

### 6.6 连接预热

消除首句冷启动延迟——页面加载时即建立所有连接：

```
用户打开页面 (onMount)
  │
  ├── ① 建立后端 WebSocket ──────────────── 并行
  ├── ② Deepgram: 发起流式连接 + 发送 500ms 静音帧预热
  └── ③ DeepSeek: 发送一条空翻译预热请求
       (System: "Warm-up. Reply 'OK'.")
  
  ▼ 所有连接就绪 (~500ms)
  
状态栏显示 🟢 就绪，等待音频
  
用户开始播放音频 → 首字延迟 ~800ms（无冷启动惩罚）
```

**预热超时处理：**
- 5 秒内未完成预热 → 显示 🟡 预热中…
- 预热失败不影响使用 → 首句走冷启动路径，后续自动恢复稳态
- 用户开始播放音频时预热仍未完成 → 立即中断预热，切换为实时模式

---

## 七、Function Call + RAG 增强（Phase 2）

### 7.1 Function Call 工具集

```python
TOOLS = [
    {
        "name": "lookup_glossary",
        "description": "查询术语表，获取标准中文译法",
        "parameters": {"term": "string", "domain": "string"}
    },
    {
        "name": "resolve_acronym",
        "description": "解析缩写全称和中文译法",
        "parameters": {"acronym": "string"}
    },
    {
        "name": "search_context",
        "description": "搜索相关知识库，消歧多义词",
        "parameters": {"query": "string", "top_k": "int"}
    },
    {
        "name": "evaluate_translation",
        "description": "自评翻译质量，低分别触发重译",
        "parameters": {"source": "string", "translation": "string"}
    }
]
```

### 7.2 RAG 知识库

```
┌─────────────────────────────────────────────────────┐
│                     RAG 知识层                        │
│                                                     │
│  ┌───────────┐  ┌───────────┐  ┌─────────────────┐ │
│  │ 用户自定义  │  │ 领域预置库  │  │ 会话即时学习     │ │
│  │ ·术语对照表│  │ ·技术文档  │  │ ·已确认术语缓存  │ │
│  │ ·产品名词  │  │ ·论文     │  │ ·说话者习惯用语  │ │
│  │ ·缩写表   │  │ ·行业报告  │  │ ·话题关键词关联  │ │
│  └─────┬─────┘  └─────┬─────┘  └────────┬────────┘ │
│        └──────────────┼───────────────┘             │
│                       ▼                              │
│           ┌─────────────────────┐                   │
│           │ 向量数据库 (Chroma)   │                   │
│           │ Embedding: 本地模型   │                   │
│           └─────────────────────┘                   │
└─────────────────────────────────────────────────────┘
```

### 7.3 增强效果

| 场景 | 无 RAG/FC | 有 RAG/FC |
|------|----------|-----------|
| 听到 "Let's talk about K8s" | 直译 "K8s" | 解析为 "Kubernetes (K8s)" |
| 听到 "attention mechanism" | "注意力机制" | 检索上下文 → "自注意力机制 (Self-Attention)" |
| 专业术语反复出现 | 每次翻译可能不同 | 会话缓存保证一致性 |
| 听到 "GPT-4o with 128K context" | 直译 | 术语表 → "128K 上下文窗口的 GPT-4o" |

---

## 八、异常处理

### 降级策略

| 故障层 | 表现 | 降级策略 |
|--------|------|---------|
| 音频流中断 | 标签页关闭/静音 | 持续发静音帧，10s 无音频→提示 |
| WebSocket 断开 | 网络抖动/重启 | 指数退避重连 (1s→2s→4s→max 30s) |
| ASR 不可用 | 超时/限流 | 自动切换 Azure Speech |
| DeepSeek 不可用 | 超时/限流 | 自动切换 GPT-4o-mini |
| 双路翻译均断 | — | 前端显示英文原文 |
| TTS 不可用 | 浏览器不支持 | 静默降级：仅字幕 |
| 修正引擎异常 | 检测逻辑出错 | 跳过修正，不阻塞主流 |

### 核心原则

- **主链路优先**：ASR + 翻译是主线，TTS 和修正引擎是旁路
- **优雅降级**：任何故障至少保证字幕可用
- **状态透明**：顶部状态栏实时显示服务商和健康状态

---

## 九、测试策略

| 层级 | 范围 | 工具 |
|------|------|------|
| 单元测试 | Provider 实现、修正检测逻辑、消息路由 | pytest + pytest-asyncio |
| 集成测试 | WS 协议、音频→字幕全链路 | pytest + 模拟 WS 客户端 |
| E2E | 浏览器完整流程 | Playwright |
| 性能 | 端到端延迟、并发压力 | locust |

### 核心测试场景

```
ASR:
  ✓ 静音段不出字幕
  ✓ 短句/长句正确处理
  ✓ 中英混杂区分

翻译:
  ✓ 简单陈述句准确翻译
  ✓ 技术术语一致性
  ✓ 长难句断句合理
  ✓ 流式输入不重复翻译

修正:
  ✓ 术语冲突检测
  ✓ 指代消解修正
  ✓ 无误修正（避免误触发）
  ✓ 修正成本控制

降级:
  ✓ ASR 断连自动切换
  ✓ 翻译超时自动切换
  ✓ 双路均断显示原文
  ✓ WS 断连自动恢复
```

---

## 十、已知局限

1. **跨句长距离依赖**：层级化上下文（Layer 2 摘要 + Layer 1 术语表）大幅缓解了此问题，但超出 5 分钟的远距离依赖仍无法回溯修正
2. **文化负载词/隐喻**：需要世界知识，实时场景下可能字面直译，Phase 2 的 RAG 将部分缓解
3. **口音/极快语速**：ASR 源头出错 → 下游全错，修正能力有限
4. **修正闪烁**：置信度门控（semantic diff < 0.3 不修正）+ 静默窗口双层防护，闪烁已最小化
5. **TTS 音色单一**：浏览器内置 `zh-CN` 音色不如商业 TTS 自然，Phase 2 可切换云端 TTS
6. **Embedding 服务依赖**：修正置信度门控需要 Embedding 服务（本地模型或 API），如不可用则退化为仅 LLM 裁决模式

---

## 十一、分阶段规划

### Phase 1 — MVP
- 基础流式管道（Deepgram + DeepSeek + WebSocket）
- 客户端预处理过滤（Interim 过滤 + 句子完整性预判）
- 连接预热（消除冷启动延迟）
- 字幕渲染（悬浮窗 + 影院双模式）
- 浏览器 TTS（含智能分块朗读）
- 修正引擎（层级化上下文 + 置信度门控 + 三维修正）
- 异常降级与自动切换

### Phase 2 — 增强
- Function Calling 集成
- RAG 知识库（Chroma + Embedding）
- 用户自定义术语表上传
- 会话即时学习

### Phase 3 — 扩展
- 多语言支持
- 桌面端应用
- 本地部署选项
- 移动端适配

---

## 十二、技术依赖

### 前端
- React 18+ / TypeScript
- Vite (构建工具)
- WebSocket API (原生)
- Web Speech API (SpeechSynthesis)
- getDisplayMedia API (音频捕获)

### 后端
- Python 3.11+ / FastAPI
- Deepgram SDK
- OpenAI SDK (兼容 DeepSeek API)
- sentence-transformers (Embedding，修正置信度门控)
- Chroma (Phase 2)

### 外部服务
- Deepgram (流式 ASR)
- DeepSeek API (翻译)
- OpenAI API (备用翻译)
- Azure Speech Services (备用 ASR)
