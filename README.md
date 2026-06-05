# AI 同声传译助手

基于大模型的 Web 端实时 AI 同声传译工具。捕获浏览器标签页音频，通过 Deepgram 流式语音识别 + DeepSeek 流式翻译，实时生成中文字幕并语音朗读，帮助用户在观看英文演讲、技术分享、国际会议和网课时跨越语言障碍。

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- Chrome / Edge 浏览器（需支持 `getDisplayMedia` 音频捕获）

### 1. 克隆项目

```bash
git clone https://github.com/diligent-zhang/ai-simultaneous-interpreter.git
cd ai-simultaneous-interpreter
```

### 2. 启动后端

```bash
cd server
cp .env.example .env          # 编辑 .env 填入 API Key
pip install -r requirements.txt
python main.py                # → http://0.0.0.0:8000
```

### 3. 启动前端

```bash
cd client
npm install
npm run dev                   # → http://localhost:5173
```

### 4. 使用

1. 打开 `http://localhost:5173`
2. 在另一个标签页播放英文视频/音频
3. 点击右上角 **开始捕获** → 选择播放音频的标签页 → 勾选「分享音频」
4. 字幕浮层实时显示英文原文 + 中文译文，TTS 自动朗读中文

> **提示:** 为避免中英文同时播放，建议**手动将源标签页静音**，仅依赖 TTS 中文朗读。

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (Browser)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐  │
│  │ 音频捕获层 │  │ 字幕渲染层 │  │ TTS 播放层 │  │  设置面板 UI  │  │
│  │          │  │          │  │          │  │              │  │
│  │getDisplay│  │ 双语浮层  │  │SpeechSyn │  │  影院/悬浮窗  │  │
│  │Media API │  │ +修正动画 │  │ thesis   │  │  字号/行数    │  │
│  └────┬─────┘  └────▲─────┘  └────▲─────┘  └───────────────┘  │
│       │              │             │                            │
│  ┌────▼──────────────▼─────────────▼──────────────────────────┐ │
│  │              WebSocket 客户端 (自动重连 + 心跳)              │ │
│  └────────────────────────┬───────────────────────────────────┘ │
└───────────────────────────┼─────────────────────────────────────┘
                            │  PCM 16kHz 16bit mono / JSON
┌───────────────────────────┼─────────────────────────────────────┐
│                           │          后端 (Python FastAPI)       │
│  ┌────────────────────────▼──────────────────────────────────┐  │
│  │                    WebSocket 消息路由                       │  │
│  └───┬──────────────────┬──────────────────┬────────────────┘  │
│      │                  │                  │                    │
│  ┌───▼──────┐   ┌───────▼──────┐   ┌──────▼──────────────┐    │
│  │ ASR 服务  │   │  翻译服务     │   │   修正引擎 (Sidecar) │    │
│  │ Deepgram │   │  DeepSeek    │   │   Correction        │    │
│  │ 流式识别  │   │  流式翻译     │   │   Engine            │    │
│  │          │   │              │   │                     │    │
│  │ 中间结果  │   │ +InterimFilter│   │  三层上下文窗口      │    │
│  │ + Final  │   │ +结构感知Prompt│   │  三维冲突检测        │    │
│  └───┬──────┘   └───────┬──────┘   │  置信度门控          │    │
│      │                  │           └──────────┬──────────┘    │
│      │           ┌──────▼──────┐               │               │
│      │           │  会话状态    │◄──────────────┘               │
│      │           │  Session    │                                │
│      └───────────┴─────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

### 技术选型

| 组件 | 主选 | 说明 |
|------|------|------|
| **音频捕获** | `getDisplayMedia` API | 捕获浏览器标签页 + 系统音频 |
| **ASR 语音识别** | Deepgram Streaming (`nova-3`) | 流式识别 + 中间结果，延迟 ~300ms |
| **翻译引擎** | DeepSeek (`deepseek-chat`) | OpenAI 兼容 API，中文翻译质量好 |
| **TTS 朗读** | 浏览器 `SpeechSynthesis` | 零成本，零额外延迟，智能分块播放 |
| **修正引擎** | 自研（规则 + Embedding + LLM） | 层级上下文 + 置信度门控 |
| **Embedding** | `sentence-transformers` | 多语言 MiniLM 模型，修正语义门控 |
| **后端框架** | Python FastAPI + WebSocket | 异步高并发，ASR/LLM SDK 生态好 |
| **前端框架** | React 19 + TypeScript + Vite | 组件化，类型安全，HMR 热更新 |

---

## 功能详解

### 1. 音频捕获与预处理

使用 `getDisplayMedia` API 捕获浏览器标签页音频，通过 `AudioContext` + `ScriptProcessorNode` 处理为 **PCM 16kHz 16bit mono** 格式，每 40ms 发送一帧（640 bytes）。通过 **零增益 GainNode**（gain=0）静音原声回放，确保用户仅听到 TTS 中文朗读，避免中英文叠加。

```
标签页音频 → MediaStream → AudioContext(16kHz) → ScriptProcessor → PCM帧 → WebSocket
                                                    │
                                            GainNode(gain=0) → destination (静音)
```

### 2. 流式语音识别 (ASR)

后端通过 `asyncio.Queue` 桥接 WebSocket 音频帧与 Deepgram WebSocket 连接。每个客户端拥有独立的 ASR 实例和音频队列，通过 `DeepgramProvider` 封装 `deepgram-sdk` 的 `listen_websocket()` 方法，回调驱动的识别结果通过 `asyncio.Queue` 转为 `AsyncIterator[ASRResult]`。

- **Interim 结果**：实时推送前端显示为灰色斜体英文草稿
- **Final 结果**：显示为正常英文，同时进入翻译管线
- **降级策略**：无 API Key 时自动切换为 Echo 回显模式

### 3. 智能过滤 (InterimFilter)

在 ASR 与翻译之间插入三层过滤，将 LLM 调用次数从 **20+ 次/句 降至 3-5 次/句**，成本降低约 75%：

| 过滤层 | 规则 | 耗时 |
|--------|------|------|
| **语气词排除** | 匹配 `um/uh/er/hmm` 等无意义填充词 | <0.1ms |
| **增量门控** | 文本变化 < 3 字符 → 跳过 | <0.1ms |
| **时间限流** | 距上次发送 < 200ms → 跳过 | <0.1ms |
| **完整性预判** | 句末标点 / 主谓结构 / 超时 3s / 长度 >50 | <0.5ms |

### 4. 结构感知翻译

翻译 Prompt 内建多层级规则，避免逐词直译：

- **`<<WAIT>>` 机制**：不完整语义片段返回等待信号，LLM 不强行翻译
- **语序调整**：英文后置定语/状语自动转换为中文前置语序
- **代词消解**：`it/this/they` 根据上文还原为具体名词
- **多义词消歧**：结合上下文选择正确的译法
- **术语保留**：专有名词保持原文形式（如 "Transformer 模型"）

翻译通过 DeepSeek 的 `stream=True` 流式输出，首 token 延迟约 500ms，中文译文逐字推送到前端。

### 5. TTS 语音合成

浏览器 `SpeechSynthesis` API 实现中文朗读，关键优化：

- **智能分块**：在自然断点（逗号、句号等）处分割，每段 ≤150 字，避免 Chrome 长文本截断 bug
- **追进度机制**：播放队列积压超过 3 句时，自动清空队列直接播最新译文
- **独立音量控制**：TTS 音量与系统音量分离，可在设置面板调节 0-100%
- **模式联动**：翻译 final 句段自动触发朗读，修正句段不重新朗读

### 6. 修正引擎 (Correction Engine)

Sidecar 模式运行，不阻塞主翻译管线。基于三层层级化上下文窗口（总计约 1300 tokens）：

```
┌──────────────────────────────────────────────┐
│  Layer 1: 关键术语表 (全会话持续)              │
│  "transformer" → "Transformer 模型"          │
│  大小: ~500 tokens, LRU 淘汰, 永不逐出         │
├──────────────────────────────────────────────┤
│  Layer 2: 话题摘要 (最近 5 分钟)               │
│  每 ~2 分钟自动生成, ~500 tokens               │
├──────────────────────────────────────────────┤
│  Layer 3: 最近原文 verbatim (最近 3 句)        │
│  ~300 tokens, 保证语篇连贯                    │
└──────────────────────────────────────────────┘
```

**三维冲突检测：**

| 维度 | 触发条件 | 处理方式 |
|------|---------|---------|
| 术语一致性 | 同一英文词前后译法不同 | 术语表规则匹配 → 直接替换 |
| 指代消解 | 代词指向前文未明确的概念 | 携带完整上下文 → LLM 重译 |
| 语义连贯 | 前后句存在因果/转折但翻译未体现 | LLM 判断指代 → 替换为具体名词 |

**置信度门控**（基于 `sentence-transformers` 计算语义余弦距离）：

```
语义差异 < 0.3  → 近义词替换，跳过修正
0.3 ≤ 差异 ≤ 0.5 → LLM 裁决是否修正
差异 > 0.5       → 明显错误，直接修正
```

**成本控制：**
- 每 segment 最多修正 2 次（防闪烁）
- 全会话最多 20 次 LLM 修正调用
- Embedding 不可用时自动降级为 Jaccard 字符相似度

### 7. 两种呈现模式

| | 悬浮窗模式 (默认) | 影院模式 |
|------|------|------|
| 适用场景 | 网页浏览、会议、网课 | 全屏视频、电影 |
| 背景 | 半透明黑底 `rgba(0,0,0,0.75)` | 透明 + 文字阴影描边 |
| 最大行数 | 2-8 行可调 | 固定 2 行 |
| 字号 | 14-36px 可调 | 缩小 20% |
| 修正动画 | 有（金色闪烁） | 无（静默替换） |
| 穿透点击 | 是 | 是 |

### 8. 降级策略

| 故障层 | 表现 | 降级策略 |
|--------|------|---------|
| 音频流中断 | 标签页关闭/静音 | 持续发静音帧 |
| WebSocket 断开 | 网络抖动 | 指数退避重连 (1s→2s→4s→max 30s) |
| ASR 不可用 | 无 API Key / 超时 | 自动切换 Echo 回显模式 |
| 翻译不可用 | 无 API Key / 超时 | 仅出英文 ASR 字幕，中文翻译缺失 |
| 双路翻译均断 | — | 前端显示英文原文 |
| TTS 不可用 | 浏览器不支持 | 静默降级：仅字幕 |
| 修正引擎异常 | Embedding 不可用 | Jaccard fallback，不阻塞主流 |
| Embedding 不可用 | 模型未安装 | 退化为字符级 Jaccard 相似度 |

**核心原则**：主链路（ASR + 翻译）优先，TTS 和修正引擎为旁路，任何故障至少保证字幕可用。

### 9. 连接预热

页面加载时（`App` 组件 `onMount`）即建立 WebSocket 连接并发送心跳，消除用户点击"开始捕获"后的冷启动延迟：

```
用户打开页面
  ├── ① 建立 WebSocket ────── 并行
  └── ② 状态栏显示 🟢 就绪

用户开始播放音频 → 首帧即传输，无连接建立延迟
```

---

## 项目结构

```
ai-simultaneous-interpreter/
├── server/                          # 后端 (Python FastAPI)
│   ├── main.py                      # 入口：WebSocket 端点 + 管线编排
│   ├── config.py                    # 环境变量配置管理
│   ├── requirements.txt             # Python 依赖
│   ├── .env.example                 # 环境变量模板
│   │
│   ├── models/
│   │   └── messages.py              # WebSocket 消息协议 (Pydantic)
│   │
│   ├── asr/                         # 语音识别模块
│   │   ├── base.py                  # ASRProvider 抽象接口
│   │   ├── types.py                 # ASRConfig, ASRResult
│   │   ├── deepgram_provider.py     # Deepgram 流式实现
│   │   └── filter.py                # InterimFilter + 完整性预判
│   │
│   ├── translator/                  # 翻译模块
│   │   ├── base.py                  # TranslationProvider 抽象接口
│   │   ├── types.py                 # TranslationConfig, TranslationResult
│   │   ├── deepseek_provider.py     # DeepSeek 流式实现
│   │   └── prompt.py                # 结构感知翻译 Prompt
│   │
│   ├── correction/                  # 修正引擎模块
│   │   ├── engine.py                # CorrectionEngine (Sidecar)
│   │   ├── detector.py              # ConflictDetector 三维检测
│   │   └── types.py                 # CorrectionEvent, CorrectionReason
│   │
│   ├── session/
│   │   └── context_window.py        # 三层上下文窗口
│   │
│   └── embedding/
│       └── embedder.py              # Embedding 服务 + 置信度门控
│
├── client/                          # 前端 (React + TypeScript + Vite)
│   ├── src/
│   │   ├── main.tsx                 # 入口
│   │   ├── App.tsx                  # 根组件：状态管理 + 管线编排
│   │   ├── App.css                  # 应用级样式 + 影院模式
│   │   ├── index.css                # 全局样式重置
│   │   │
│   │   ├── types/
│   │   │   └── messages.ts          # 消息协议类型定义
│   │   │
│   │   ├── services/
│   │   │   └── websocket.ts         # WebSocket 客户端单例
│   │   │
│   │   ├── hooks/
│   │   │   ├── useAudioCapture.ts   # 标签页音频捕获
│   │   │   ├── useTTS.ts            # TTS 智能分块朗读
│   │   │   └── useSettings.ts       # 设置持久化 (localStorage)
│   │   │
│   │   └── components/
│   │       ├── AudioCapture.tsx      # 捕获控制 + 状态栏
│   │       ├── SubtitleOverlay.tsx   # 双语字幕浮层 + 修正动画
│   │       └── SettingsPanel.tsx     # 抽屉式设置面板
│   │
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
│
└── docs/
    └── superpowers/
        ├── specs/                   # 设计文档
        │   └── 2026-06-05-ai-interpretation-assistant-design.md
        └── plans/                   # 实现计划 (Slices 1-5)
```

---

## 配置说明

在 `server/.env` 中配置 API Key：

```bash
# 服务端口
HOST=0.0.0.0
PORT=8000

# Deepgram (流式 ASR) — 必需，否则仅 Echo 模式
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPGRAM_MODEL=nova-3
DEEPGRAM_LANGUAGE=en

# DeepSeek (翻译) — 可选，不配则仅出英文 ASR 字幕
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# OpenAI (备用翻译，Phase 2)
OPENAI_API_KEY=

# Azure Speech (备用 ASR，Phase 2)
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=

# 修正引擎
CORRECTION_ENABLED=true
MAX_CORRECTION_CALLS=20
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
```

### 获取 API Key

- **Deepgram**：https://console.deepgram.com → 注册即送 $200 额度
- **DeepSeek**：https://platform.deepseek.com → 注册即送额度，中文翻译性价比极高

---

## API 协议

### WebSocket 端点

```
ws://localhost:8000/ws
```

### 客户端 → 服务端

| 消息类型 | 格式 | 说明 |
|---------|------|------|
| `audio_frame` | 二进制 | PCM 16kHz 16bit mono, 640 bytes/帧 (40ms) |
| `ping` | JSON `{"type":"ping"}` | 心跳 (30s 间隔) |
| `config` | JSON `{"type":"config",...}` | 源/目标语言、ASR/翻译提供商 |

### 服务端 → 客户端

| 消息类型 | 关键字段 | 说明 |
|---------|---------|------|
| `subtitle` | `segment_id, text, is_final, source, confidence` | ASR 原文 (`asr`) 或翻译 (`translation`) |
| `correction` | `segment_id, old_text, new_text, reason, confidence` | 修正事件 |
| `status` | `asr_status, translation_status, latency_ms` | 服务商 + 延迟 |
| `pong` | — | 心跳响应 |

---

## 延迟预算

**稳态延迟（预热后）：**

| 环节 | 目标延迟 | 说明 |
|------|---------|------|
| 浏览器音频采集 | ~20ms | 40ms/帧，采集即发 |
| 客户端预处理过滤 | ~1ms | Interim 过滤 + 完整性预判 |
| 网络传输 (上行) | ~50ms | PCM 原始音频 |
| Deepgram ASR (首 interim) | ~300ms | 流式 API（连接已预热） |
| DeepSeek 翻译 (首 token) | ~500ms | 流式输出（连接已预热） |
| 网络传输 (下行) | ~50ms | JSON <1KB |
| 前端渲染 + TTS 启动 | ~50ms | TTS 分块预加载 |
| **稳态总计** | **~971ms** | 低于 1-3s 同传目标 |

---

## 已知局限

1. **DRM 内容**：Netflix、Disney+ 等流媒体平台的音频受 DRM 保护，`getDisplayMedia` 捕获到的音频轨道为静音
2. **会议场景**：Zoom/Teams 中共享屏幕时，Chrome 不允许同时捕获该标签页音频
3. **浏览器兼容**：Firefox/Safari 不支持 `getDisplayMedia({audio: true})` 的系统音频捕获，仅限 Chrome/Edge
4. **原声消音**：浏览器无法自动静音源标签页，用户需手动将源标签页静音以避免中英文重叠
5. **跨句长距离依赖**：层级化上下文窗口缓解了此问题，但超过 5 分钟的远距离依赖仍无法回溯修正
6. **TTS 音色**：浏览器内置 `zh-CN` 音色不如商业 TTS 自然，Phase 2 可切换云端 TTS
7. **ScriptProcessorNode**：已弃用的 API，后续需迁移到 AudioWorklet

---

## Roadmap

### Phase 1 — MVP ✅

- [x] 基础流式管道（Deepgram + DeepSeek + WebSocket）
- [x] 客户端预处理过滤（Interim 过滤 + 句子完整性预判）
- [x] 连接预热（消除冷启动延迟）
- [x] 字幕渲染（悬浮窗 + 影院双模式）
- [x] 浏览器 TTS（含智能分块朗读）
- [x] 修正引擎（层级化上下文 + 置信度门控 + 三维修正）
- [x] 异常降级与自动切换
- [x] 设置面板（字号/行数/模式/TTS/修正）

### Phase 2 — 增强

- [ ] Function Calling 集成（术语表查询、缩写解析、上下文搜索）
- [ ] RAG 知识库（Chroma + Embedding，用户自定义术语表）
- [ ] 会话即时学习（已确认术语缓存、说话者习惯用语）
- [ ] 云端 TTS 切换（Azure/Edge TTS）

### Phase 3 — 扩展

- [ ] 多语言支持
- [ ] 桌面端应用（Electron/Tauri）
- [ ] 本地部署选项（Ollama + Whisper）
- [ ] 移动端适配

---

## License

MIT
