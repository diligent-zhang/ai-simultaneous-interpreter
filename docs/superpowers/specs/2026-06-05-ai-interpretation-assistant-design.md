# AI 同声传译助手 — 设计文档

> 版本: v1.0 | 日期: 2026-06-05 | 状态: 待实现

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

### 4.2 三层递进翻译策略

#### 第一层：智能分块（Chunking）

不做逐词翻译，也不等完整句子。在自然语义断点处翻译。

- LLM 判断当前输入是否构成可翻译的完整语义单元
- 不完整时返回等待信号，不强行翻译
- 减少因语序差异导致的回溯修正

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

### 4.3 修正消息协议

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

### 4.4 修正静默窗口

- final 后 2 秒内：允许静默修正（用户不易察觉）
- final 后超过 2 秒：修正时前端不做动画（影院模式）/ 做轻动画（悬浮窗模式）
- 同一 segment 最多修正 2 次，避免反复闪烁

---

## 五、前端设计

### 5.1 组件树

```
App
├── AudioCapture          ← 音频源选择 + 捕获
│   ├── TabCapture        ← 浏览器标签页捕获 (getDisplayMedia)
│   └── SystemAudio       ← 系统音频 (后续桌面端)
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

- 浏览器 `SpeechSynthesis API`，音色 `zh-CN`
- 播放队列：每个 stable 句段入队
- 追进度机制：队列 >3 句积压 → 跳过中间句，直接播最新
- 被修正句段不重新朗读

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
├── session/
│   ├── manager.py           ← 会话管理器
│   └── context_window.py    ← 滑动上下文窗口
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

### 6.4 修正引擎

```
核心流程:
1. 每个 final 句段进入:
   a. 追加到滑动窗口 (最近 10 句或 ~2000 tokens，以先达到者为准)
   b. 提取关键术语 + 指代链
   c. 与窗口内历史句段做冲突检测

2. 冲突检测维度:
   · 术语一致性: 同一英文词前后译法不同
   · 指代消解: 代词指向不明确，上下文已澄清
   · 语义连贯: 前后句存在因果/转折但翻译未体现

3. 修正策略:
   · 小修正 (术语替换): 本地规则，不调用 LLM (<5ms)
   · 大修正 (指代/语序): 调用 LLM 重译 (~300ms)
   · 成本控制: 单次会话最多 20 次 LLM 修正调用

4. 输出:
   · 修正事件 {type, segment_id, old_text, new_text, reason}
```

### 6.5 延迟预算

| 环节 | 目标延迟 | 说明 |
|------|---------|------|
| 浏览器音频采集 | ~20ms | 40ms/帧，采集即发 |
| 网络传输 (上行) | ~50ms | PCM 原始音频 |
| Deepgram ASR (首 interim) | ~300ms | 流式 API |
| DeepSeek 翻译 (首 token) | ~500ms | 流式输出 |
| 网络传输 (下行) | ~50ms | 单句 JSON <1KB |
| 前端渲染 + TTS 启动 | ~50ms | 瞬时 |
| **总计** | **~970ms** | 低于 3s 目标 |

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

1. **跨句长距离依赖**：超出滑动窗口的上下文无法回溯修正
2. **文化负载词/隐喻**：需要世界知识，实时场景下可能字面直译
3. **口音/极快语速**：ASR 源头出错 → 下游全错，修正能力有限
4. **修正闪烁**：同一句修正 >2 次用户会察觉，通过静默窗口控制

---

## 十一、分阶段规划

### Phase 1 — MVP
- 基础流式管道（Deepgram + DeepSeek + WebSocket）
- 字幕渲染（悬浮窗 + 影院双模式）
- 浏览器 TTS
- 基础修正引擎（术语一致性）
- 异常降级

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
- Chroma (Phase 2)

### 外部服务
- Deepgram (流式 ASR)
- DeepSeek API (翻译)
- OpenAI API (备用翻译)
- Azure Speech Services (备用 ASR)
