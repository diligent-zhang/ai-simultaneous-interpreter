# AI 同声传译助手

> Web 优先的实时 AI 同声传译工具 — 捕获浏览器标签页音频，Deepgram 流式 ASR + DeepSeek 流式翻译 + RAG 术语增强，实时生成中文字幕并语音朗读。

[![Python](https://img.shields.io/badge/Python-3.11+-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-6.0-3178C6)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF)](https://vite.dev/)

---
视频demo项目演示   https://www.bilibili.com/video/BV1YhEb6JEpy/?vd_source=83956e5d3c7537af89915113f8216731
## 目录

- [快速开始](#快速开始)
- [架构概览](#架构概览)
- [功能详解](#功能详解)
- [项目结构](#项目结构)
- [配置说明](#配置说明)
- [API 文档](#api-文档)
- [延迟预算](#延迟预算)
- [异常降级](#异常降级)
- [已知局限](#已知局限)
- [路线图](#路线图)

---

## 快速开始

### 环境要求

- **Python** ≥ 3.11
- **Node.js** ≥ 22
- **Chrome / Edge** 浏览器（需支持 `getDisplayMedia({ audio: true })`）

### 1. 克隆项目

```bash
git clone https://github.com/diligent-zhang/ai-simultaneous-interpreter.git
cd ai-simultaneous-interpreter
```

### 2. 启动后端

```bash
cd server

# 创建虚拟环境
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置 API Key（编辑 .env 文件）
cp .env.example .env
```

**.env 最小配置：**

```env
DEEPGRAM_API_KEY=your_deepgram_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
```

```bash
# 启动服务 → http://localhost:8000
python main.py
```

### 3. 启动前端

```bash
cd client
npm install
npm run dev                  # → http://localhost:5173
```

### 4. 使用

1. 浏览器打开 `http://localhost:5173`
2. 在另一个标签页播放英文视频/音频
3. 点击 **"开始捕获"** → 选择播放音频的标签页 → 勾选 **"分享音频"**
4. 字幕浮层实时显示 **英文原文** + **中文译文**，TTS 自动朗读中文
5. 点击 ⚙️ 进入设置面板（字号/行数/影院模式/TTS/修正开关）

> **提示：** 建议手动将源标签页静音，避免中英文声音叠加。

### 获取 API Key

| 服务 | 注册地址 | 说明 |
|------|---------|------|
| Deepgram (ASR) | https://console.deepgram.com | 注册送 $200 额度 |
| DeepSeek (翻译) | https://platform.deepseek.com | 注册送额度，中文性价比高 |

---

## 架构概览

```
┌──────────────────────────────────────────────────────────────────────┐
│                          浏览器 (React 19)                            │
│                                                                      │
│  getDisplayMedia()      SubtitleOverlay       Edge TTS / Speech API  │
│  标签页音频捕获 (40ms/帧)  双语字幕浮层           流式语音合成          │
│        │                      ▲                       ▲              │
│        └──────────────────────┼───────────────────────┘              │
│                               │                                      │
│                      WebSocket (JSON + 二进制 PCM)                    │
└───────────────────────────────┼──────────────────────────────────────┘
                                │
┌───────────────────────────────┼──────────────────────────────────────┐
│                               │        后端 (Python FastAPI)          │
│                               ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    WebSocket 消息路由                          │   │
│  │       音频帧 → ASR 管道 | 翻译结果 ← LLM | 修正事件 → 前端     │   │
│  └────┬──────────────────┬────────────────────┬─────────────────┘   │
│       │                  │                    │                      │
│  ┌────▼──────┐   ┌───────▼──────┐   ┌─────────▼──────────┐          │
│  │ Deepgram  │   │   DeepSeek   │   │   修正引擎 (Sidecar) │          │
│  │ 流式 ASR  │   │   流式翻译    │   │   三层上下文窗口     │          │
│  │ + 中间结果│   │ + RAG 术语注入│   │   冲突检测 + 门控    │          │
│  │ + 重连机制│   │ + 结构感知    │   │   术语表/摘要/原文   │          │
│  └────┬──────┘   └───────┬──────┘   └─────────┬──────────┘          │
│       │                  │                     │                     │
│       │           ┌──────▼──────┐              │                     │
│       │           │  RAG 知识库  │◄─────────────┘                     │
│       │           │  ChromaDB + │                                     │
│       │           │  Embedding  │                                     │
│       └───────────┴─────────────┘                                     │
└──────────────────────────────────────────────────────────────────────┘
```

### 数据流时序

```
说话者:  "Artificial intelligence...  is transforming...   every industry..."

ASR 中间: "Artif..."(0.3s)   "AI is trans..."(1.2s)   "AI is transforming
                                                        every industry"(2.1s)

翻译输出:  "人工..."(0.5s)    "人工智能正在改变..."(1.5s)  "人工智能正在重塑
                                                         每一个行业"(2.5s)

修正引擎:                                           ┌──────────────────────┐
  "transforming" 结合后文语义                          │ 修正: 改变 → 重塑    │
  应译为"重塑"而非"改变" ──────────────────────────▶  │ confidence: 0.92     │
                                                     └──────────────────────┘
```

---

## 功能详解

### 1. 音频捕获与预处理

`getDisplayMedia` API 捕获浏览器标签页音频 → `AudioContext` 重采样为 **PCM 16kHz 16bit mono** → 每 40ms 发送 640 字节帧 → WebSocket 上传。

```
标签页音频 → MediaStream → AudioContext(16kHz) → ScriptProcessor → PCM帧 → WebSocket
                                                    │
                                            GainNode(gain=0) → 静音原声回放
```

通过零增益 GainNode 将捕获的音频静音回放，确保用户仅听到 TTS 中文朗读。

### 2. 流式 ASR（Deepgram）

后端通过 `asyncio.Queue` 桥接 WebSocket 音频帧与 Deepgram WebSocket 连接：

- **Interim 结果**：实时推送前端，显示为灰色斜体英文草稿
- **Final 结果**：显示为正常英文文本，同时进入翻译管线
- **断线重连**：Deepgram 连接断开后自动重连（最多 5 次），等待新音频帧到达后恢复
- **降级模式**：未配置 API Key 时自动切换为 Echo 回显模式（显示音频帧大小）

### 3. 客户端智能过滤（InterimFilter）

在 ASR 和翻译之间插入三层过滤，将 LLM 调用从 **20+ 次/句降至 3-5 次/句**，成本降低约 75%：

| 过滤层 | 规则 | 耗时 |
|--------|------|------|
| 语气词排除 | 匹配 `um/uh/er/hmm` 等无意义填充词 | <0.1ms |
| 增量门控 | 文本变化 < 2 字符 → 跳过 | <0.1ms |
| 时间限流 | 距上次发送 < 200ms → 跳过 | <0.1ms |
| 完整性预判 | 句末标点 / 主谓结构 / 超时 3s / 长度 >50 | <0.5ms |

### 4. 结构感知翻译（DeepSeek + RAG）

翻译 Prompt 内建多层级规则，配合 RAG 术语检索实现专业级翻译：

- **RAG 术语注入**：翻译前自动检索 ChromaDB 知识库，将匹配术语注入 Prompt（如 `"transformer" → "Transformer 模型"`）
- **`<<WAIT>>` 机制**：不完整语义片段返回等待信号，不强行翻译
- **语序调整**：英文后置定语/状语 → 中文前置语序
- **代词消解**：`it/this/they` 根据上下文还原为具体名词
- **术语保留**：专有名词保持原文形式（如 "Transformer 模型"、"API 接口"）
- **流式输出**：DeepSeek `stream=True`，中文增量 ≥ 2 字即推送到前端，消除等待感

### 5. TTS 语音朗读（双路径）

| 模式 | 实现 | 特点 |
|------|------|------|
| **Edge TTS**（默认） | 服务端 `/api/tts` → Microsoft Edge TTS 流式合成 MP3 → 前端 AudioContext 双缓冲播放 | 音色自然，无间隙播放 |
| **Browser**（降级） | 浏览器 `SpeechSynthesis` API | 零延迟，离线可用 |

关键优化：
- **激进流式朗读**：翻译每新增 2+ 字即朗读增量，Final 时完整朗读
- **智能分块**：在自然断点（逗号/句号）处分割，每段 ≤ 150 字
- **追进度机制**：新内容到达时中断当前朗读，直接播最新译文
- **独立音量控制**：TTS 音量与系统音量分离

### 6. 修正引擎（Correction Engine）

Sidecar 模式运行，不阻塞主翻译管线。基于三层上下文窗口（合计 ~1300 tokens）：

```
┌──────────────────────────────────────────────┐
│  Layer 1: 关键术语表（全会话持续）             │
│  "transformer" → "Transformer 模型"          │
│  ~500 tokens, LRU 淘汰, 永不逐出              │
├──────────────────────────────────────────────┤
│  Layer 2: 话题摘要（最近 5 分钟）              │
│  每 ~2 分钟自动生成, ~500 tokens              │
├──────────────────────────────────────────────┤
│  Layer 3: 最近原文 verbatim（最近 3 句）       │
│  ~300 tokens, 保证语篇连贯                    │
└──────────────────────────────────────────────┘
```

**三维冲突检测：**

| 维度 | 触发条件 | 处理方式 |
|------|---------|---------|
| 术语一致性 | 同一英文词前后译法不同 | 术语表规则匹配 → 直接替换 (<5ms) |
| 指代消解 | 代词指向前文未明确的概念 | 携带完整上下文 → LLM 重译 (~300ms) |
| 语义连贯 | 前后句因果/转折翻译未体现 | LLM 判断 + 替换为具体名词 |

**置信度门控**（基于 `sentence-transformers` 语义余弦距离）：

```
语义差异 < 0.3  → 近义词替换，跳过修正（避免闪烁）
0.3 ≤ 差异 < 0.5 → LLM 裁决是否修正
差异 ≥ 0.5       → 明显错误，直接修正
```

**成本控制**：每 segment 最多修正 2 次，全会话最多 20 次 LLM 修正调用。

### 7. 字幕双模式

| | 悬浮窗模式（默认） | 影院模式 |
|---|---|---|
| 适用场景 | 网页/会议/网课 | 全屏视频/电影 |
| 背景 | 半透明黑底 `rgba(0,0,0,0.75)` | 透明 + 文字阴影描边 |
| 最大行数 | 2-8 行可调 | 固定 2 行 |
| 字号 | 14-36px 可调 | 缩小 20% |
| 修正动画 | 有（闪烁提示） | 无（静默替换） |
| 点击穿透 | ✅ | ✅ |

### 8. 连接预热

页面加载时（`App` 组件 `onMount`）即建立 WebSocket 连接，消除"开始捕获"后的冷启动：

```
用户打开页面
  ├── ① 建立 WebSocket ───── 预热 ~200ms
  └── ② 状态栏显示 🟢 就绪

用户开始播放音频 → 首帧即传输，首字延迟 ~800ms（无预热则 ~1.5s）
```

---

## 项目结构

```
ai-simultaneous-interpreter/
├── README.md
│
├── server/                              # Python 后端
│   ├── main.py                          # FastAPI 入口 + WebSocket 端点 + 管线编排
│   ├── config.py                        # 环境变量配置管理
│   ├── requirements.txt                 # Python 依赖
│   │
│   ├── models/
│   │   └── messages.py                  # WebSocket 消息协议 (Pydantic)
│   │
│   ├── asr/                             # 语音识别模块
│   │   ├── base.py                      # ASRProvider 抽象接口
│   │   ├── types.py                     # ASRConfig, ASRResult
│   │   ├── deepgram_provider.py         # Deepgram 流式实现 + 断线重连
│   │   └── filter.py                    # InterimFilter + 句子完整性预判
│   │
│   ├── translator/                      # 翻译模块
│   │   ├── base.py                      # TranslationProvider 抽象接口
│   │   ├── types.py                     # TranslationConfig, TranslationResult
│   │   ├── deepseek_provider.py         # DeepSeek 流式实现 + 节流去重
│   │   ├── prompt.py                    # 结构感知翻译 Prompt 模板
│   │   └── tools.py                     # RAG 术语检索 + 上下文注入
│   │
│   ├── correction/                      # 修正引擎模块
│   │   ├── engine.py                    # CorrectionEngine (Sidecar)
│   │   ├── detector.py                  # ConflictDetector 三维冲突检测
│   │   └── types.py                     # CorrectionEvent, CorrectionReason
│   │
│   ├── session/
│   │   └── context_window.py            # 三层上下文窗口 + 术语自动提取
│   │
│   ├── rag/                             # RAG 知识库模块
│   │   ├── store.py                     # ChromaDB 向量存储 (初始化 + CRUD)
│   │   ├── retriever.py                 # Embedding 相似度检索器
│   │   ├── glossary.py                  # 内置默认术语表 (~200 条 AI/CS/Business)
│   │   └── acronyms.py                  # 缩写全称解析
│   │
│   ├── embedding/
│   │   └── embedder.py                  # Embedding 服务 + 置信度门控 (should_correct)
│   │
│   ├── tts/
│   │   └── edge_provider.py             # Microsoft Edge TTS 流式合成 (edge-tts)
│   │
│   └── tests/                           # 单元测试 + 集成测试
│       ├── test_asr_filter.py
│       ├── test_correction_detector.py
│       ├── test_correction_engine.py
│       ├── test_messages.py
│       ├── test_rag_glossary.py
│       ├── test_rag_retriever.py
│       ├── test_translator_tools.py
│       ├── test_tts_edge.py
│       ├── test_session_learning.py
│       └── test_websocket_integration.py
│
├── client/                              # React 前端
│   ├── package.json
│   └── src/
│       ├── main.tsx                     # 入口
│       ├── App.tsx                      # 根组件：字幕状态管理 + WS 消息路由 + TTS 调度
│       ├── App.css                      # 应用级样式 + 影院模式
│       │
│       ├── types/
│       │   └── messages.ts              # 消息协议类型定义
│       │
│       ├── services/
│       │   └── websocket.ts             # WebSocket 客户端单例 (自动重连 + 心跳)
│       │
│       ├── hooks/
│       │   ├── useAudioCapture.ts       # 标签页音频捕获 (getDisplayMedia)
│       │   ├── useTTS.ts               # TTS 双路径合成 (Edge API / Browser)
│       │   └── useSettings.ts          # 设置持久化 (localStorage)
│       │
│       └── components/
│           ├── AudioCapture.tsx          # 捕获控制按钮 + 状态栏
│           ├── SubtitleOverlay.tsx       # 双语字幕浮层 (悬浮窗/影院双模式)
│           └── SettingsPanel.tsx         # 抽屉式设置面板
│
└── docs/                                # 设计文档
    └── superpowers/
        ├── specs/                       # 完整设计规格
        └── plans/                       # 分阶段实施计划
```

---

## 配置说明

### 服务端环境变量（server/.env）

| 变量 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `DEEPGRAM_API_KEY` | ✅ | — | Deepgram ASR API Key |
| `DEEPSEEK_API_KEY` | ✅ | — | DeepSeek 翻译 API Key |
| `HOST` | | `0.0.0.0` | 服务监听地址 |
| `PORT` | | `8000` | 服务端口 |
| `DEEPGRAM_MODEL` | | `nova-3` | Deepgram 模型 |
| `DEEPGRAM_LANGUAGE` | | `en` | ASR 识别语言 |
| `DEEPGRAM_SAMPLE_RATE` | | `16000` | 音频采样率 |
| `DEEPSEEK_MODEL` | | `deepseek-chat` | 翻译模型 |
| `DEEPSEEK_BASE_URL` | | `https://api.deepseek.com/v1` | API 地址 |
| `DEEPSEEK_TEMPERATURE` | | `0.3` | 翻译温度（低=稳定） |
| `DEEPSEEK_MAX_TOKENS` | | `1024` | 翻译最大 token 数 |
| `CORRECTION_ENABLED` | | `true` | 是否启用修正引擎 |
| `MAX_CORRECTION_CALLS` | | `20` | 单次会话最大 LLM 修正次数 |
| `RAG_ENABLED` | | `true` | 是否启用 RAG 知识库 |
| `RAG_DATA_DIR` | | `server/data/chroma` | ChromaDB 持久化目录 |
| `EMBEDDING_MODEL` | | `paraphrase-multilingual-MiniLM-L12-v2` | Embedding 模型 |
| `OPENAI_API_KEY` | | — | 备用翻译（GPT-4o-mini） |
| `AZURE_SPEECH_KEY` | | — | 备用 ASR（Azure Speech） |
| `AZURE_SPEECH_REGION` | | — | Azure 服务区域 |

### 前端设置面板（持久化到 localStorage）

| 分类 | 配置项 | 默认值 |
|------|--------|--------|
| 显示 | 字号 | 20px |
| 显示 | 最大行数 | 5 |
| 显示 | 影院模式 | 关闭 |
| TTS | TTS 开关 | 开启 |
| TTS | 语音服务商 | Edge |
| TTS | 音色 | zh-CN-XiaoxiaoNeural |
| 修正 | 修正引擎 | 开启 |

---

## API 文档

后端启动后访问 `http://localhost:8000/docs` 查看 Swagger UI。

### REST 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/health` | 健康检查 → `{"status":"ok","version":"0.4.0"}` |
| `GET` | `/api/tts?text=...&voice=...&rate=...` | 流式 TTS 合成 → `audio/mpeg` 流 |
| `GET` | `/api/glossary/stats` | 术语库统计信息（总数/领域分布） |
| `GET` | `/api/glossary/search?q=...&top_k=...` | 搜索术语 |
| `POST` | `/api/glossary/upload` | 上传自定义术语 `{"terms":[{"en":"...","zh":"...","domain":"..."}]}` |

### WebSocket 端点

```
ws://localhost:8000/ws
```

**客户端 → 服务端：**

| 消息 | 格式 | 说明 |
|------|------|------|
| 音频帧 | 二进制 | PCM 16kHz 16bit mono, 640 bytes/帧 (40ms) |
| ping | `{"type":"ping"}` | 心跳保活 |
| config | `{"type":"config",...}` | 运行时配置更新 |

**服务端 → 客户端：**

| 消息 | 关键字段 | 说明 |
|------|---------|------|
| `subtitle` | `segment_id, text, is_final, source(asr\|translation), confidence, timestamp, replace, sequence` | ASR 识别或翻译结果 |
| `correction` | `segment_id, old_text, new_text, reason, confidence` | 修正事件 |
| `status` | `asr_status, translation_status, latency_ms` | 服务商状态 + 端到端延迟 |
| `pong` | — | 心跳响应 |

---

## 延迟预算

### 稳态延迟（连接预热后）

| 环节 | 目标延迟 | 说明 |
|------|---------|------|
| 浏览器音频采集 | ~20ms | 40ms/帧，采集即发 |
| 客户端预处理过滤 | ~1ms | Interim 过滤 + 完整性预判 |
| 网络上行 | ~50ms | PCM 原始音频 |
| Deepgram ASR（首 interim） | ~300ms | 流式 API（连接已预热） |
| DeepSeek 翻译（首 token） | ~500ms | 流式输出（连接已预热） |
| 网络下行 | ~50ms | JSON < 1KB |
| 前端渲染 + TTS 启动 | ~50ms | TTS 分块预加载 |
| **稳态总计** | **~971ms** | 稳定低于 1-3s 同传目标 |

### 冷启动额外代价

| 环节 | 额外延迟 |
|------|---------|
| Deepgram WS 连接建立 | ~200ms |
| DeepSeek API 冷启动 | ~300ms |
| **冷启动总计** | **~1471ms** |

连接预热后首句延迟降至约 **800ms**。

---

## 异常降级

| 故障层 | 表现 | 降级策略 |
|--------|------|---------|
| 音频流中断 | 标签页关闭/静音 | 10s 无音频 → 提示用户 |
| WebSocket 断开 | 网络抖动 | 指数退避重连（1s → 2s → 4s → max 30s） |
| Deepgram 不可用 | 超时/限流 | → 自动切换 Azure Speech → Echo 回显模式 |
| Deepgram 断连 | 长会话中断 | 最多重连 5 次，等待新音频帧后自动恢复 |
| DeepSeek 不可用 | 超时/限流 | → 自动切换 GPT-4o-mini |
| 双路翻译均断 | — | → 前端仅显示英文 ASR 原文 |
| TTS 不可用 | Edge API 故障 | → 自动降级为浏览器 SpeechSynthesis |
| 修正引擎异常 | Embedding 不可用 | → Jaccard 字符相似度 fallback，不阻塞主流 |
| RAG 初始化失败 | ChromaDB 不可用 | → 无术语增强，正常翻译不受影响 |

**核心原则：** 主链路（ASR + 翻译）优先，TTS 和修正引擎为旁路，任何故障至少保证字幕可用。

---

## 已知局限

1. **DRM 内容**：Netflix、Disney+ 等平台的音频受 DRM 保护，`getDisplayMedia` 捕获的音频为静音
2. **会议场景**：Zoom/Teams 共享屏幕时，Chrome 不允许同时捕获该标签页音频
3. **浏览器兼容**：Firefox/Safari 不支持 `getDisplayMedia({ audio: true })`，仅 Chrome/Edge 可用
4. **原声消音**：浏览器无法自动静音源标签页，需手动将源标签页静音
5. **长距离依赖**：超过 5 分钟的上下文依赖三层窗口无法完全覆盖
6. **ScriptProcessorNode**：已弃用的 API，后续需迁移到 AudioWorklet
7. **Embedding 模型下载**：首次运行需下载 `paraphrase-multilingual-MiniLM-L12-v2`（~470MB），需要网络环境

---

## 路线图

### Phase 1 — MVP ✅ 已完成

- [x] 流式管道（Deepgram + DeepSeek + WebSocket）
- [x] 客户端预处理过滤（InterimFilter + 完整性预判）
- [x] 连接预热（消除冷启动）
- [x] 字幕双模式渲染（悬浮窗 + 影院）
- [x] 双路径 TTS（Edge TTS 流式 + Browser Speech 降级）
- [x] 上下文修正引擎（三层窗口 + 置信度门控）
- [x] RAG 知识库（ChromaDB + ~200 条内置术语 + 自定义上传）
- [x] 异常降级与自动切换
- [x] 设置面板（显示/TTS/修正）

### Phase 2 — 增强

- [ ] Function Calling 深度集成（术语查询/缩写解析/上下文搜索/自评质量）
- [ ] RAG 知识库扩展（领域预置库、文档导入）
- [ ] 用户自定义术语表管理 UI
- [ ] 会话即时学习优化
- [ ] LLM 辅助重译完整实现

### Phase 3 — 扩展

- [ ] 多语言支持（中日韩等）
- [ ] 桌面端应用（Electron / Tauri）
- [ ] 本地部署方案（Ollama + Whisper）
- [ ] 移动端适配

---

## 技术栈

| 层级 | 技术 | 版本 |
|---|---|---|
| 后端框架 | Python FastAPI + Uvicorn | 0.115 |
| 前端框架 | React + TypeScript + Vite | 19 / 6.0 / 8 |
| ASR | Deepgram SDK (nova-3) | 3.9 |
| 翻译 | DeepSeek (OpenAI 兼容 API) | — |
| Embedding | sentence-transformers (MiniLM) | 3.0 |
| 向量数据库 | ChromaDB | 0.5 |
| TTS | edge-tts (Microsoft Edge) | 6.0 |
| 数据校验 | Pydantic | 2.10 |
| WebSocket | websockets | 14.1 |

---

## License

MIT

---

<p align="center">
  <sub>Built for breaking language barriers in real-time 🌐</sub>
</p>
