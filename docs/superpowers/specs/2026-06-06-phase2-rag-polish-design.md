# Phase 2 增强 + MVP 打磨 — 设计文档

> 版本: v1.0 | 日期: 2026-06-06 | 状态: 待实现

---

## 一、范围概述

本轮在 Phase 1 MVP 基础上，综合推进两件事：

| 类别 | 内容 | 目标 |
|------|------|------|
| 🔧 打磨 | AudioWorklet 迁移 | 替换已弃用的 ScriptProcessorNode |
| 🧪 打磨 | 后端核心测试 | 补齐 pytest 测试，防止回归 |
| 🧠 Phase 2 | RAG 知识库 | ChromaDB + 默认术语表，译前检索 |
| 🔧 Phase 2 | 上下文注入 | 术语注入翻译 Prompt，提升专业度 |
| 🔌 Phase 2 | 术语管理 API | 上传/搜索/统计端点 |

**不做：** 云端 TTS 切换、会话即时学习、E2E 测试、性能压测。

---

## 二、AudioWorklet 迁移

### 2.1 当前状态

`client/src/hooks/useAudioCapture.ts` 使用 `ScriptProcessorNode` 处理音频，该 API 已被 Chrome 标记为弃用。

### 2.2 目标方案

替换为 `AudioWorkletNode`（W3C 标准，Chrome 66+ 支持）。

**新增文件：**

- `client/public/audio-processor.js` — AudioWorklet 处理器，运行在独立线程

**修改文件：**

- `client/src/hooks/useAudioCapture.ts` — `createScriptProcessor` → `audioWorklet.addModule()` + `new AudioWorkletNode()`

### 2.3 处理器设计

```javascript
// audio-processor.js — 在独立 AudioWorklet 线程中运行
class AudioProcessor extends AudioWorkletProcessor {
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];  // Float32Array, 16kHz mono
      // 转换为 PCM 16bit 并通过 MessagePort 发送到主线程
      const pcm16 = this.float32ToPCM16(channelData);
      this.port.postMessage(pcm16.buffer, [pcm16.buffer]);
    }
    return true; // 保持处理器活跃
  }

  float32ToPCM16(float32) {
    const buf = new ArrayBuffer(float32.length * 2);
    const view = new DataView(buf);
    for (let i = 0; i < float32.length; i++) {
      const s = Math.max(-1, Math.min(1, float32[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
    }
    return buf;
  }
}

registerProcessor('audio-processor', AudioProcessor);
```

### 2.4 兼容性保障

- 消息格式不变（PCM 16kHz 16bit mono，40ms/帧）
- 零增益 GainNode 静音逻辑保持不变
- 若 AudioWorklet 加载失败，保留 ScriptProcessor 降级路径

---

## 三、测试策略

### 3.1 范围

仅做后端 pytest 测试，不做前端组件测试和 E2E。

### 3.2 测试文件规划

```
server/tests/
├── __init__.py
├── conftest.py                      # fixtures: async client, mock WS
├── test_asr_filter.py               # InterimFilter 过滤逻辑
├── test_correction_detector.py      # 冲突检测三维测试
├── test_correction_engine.py        # 修正引擎核心流程
├── test_messages.py                 # WebSocket 消息模型校验
├── test_rag_retriever.py            # RAG 检索接口 (新增)
├── test_rag_glossary.py             # 术语表加载 & 搜索 (新增)
├── test_translator_tools.py         # 译前上下文构建 (新增)
└── test_websocket_integration.py    # WebSocket 端点集成
```

### 3.3 核心测试场景

```
ASR Filter:
  ✓ 语气词排除 (um/uh/er)
  ✓ 增量门控 (文本变化 < 3 字符跳过)
  ✓ 时间限流 (< 200ms 跳过)
  ✓ 完整性预判 (句末标点/超时)

修正引擎:
  ✓ 术语冲突检测
  ✓ 指代消解检测
  ✓ 无误修正（避免误触发）
  ✓ 置信度门控阈值

RAG:
  ✓ 术语检索命中
  ✓ 无匹配时返回空
  ✓ Embedding 不可用时关键词降级
  ✓ 缩写解析正确性

WebSocket:
  ✓ 连接/断开
  ✓ ping/pong 心跳
  ✓ 音频帧转发
  ✓ 无效消息拒绝
```

---

## 四、RAG 知识库

### 4.1 技术选型

| 维度 | 方案 |
|------|------|
| 向量数据库 | ChromaDB（持久化到 `server/data/chroma/`） |
| Embedding | 复用现有 `paraphrase-multilingual-MiniLM-L12-v2` |
| 默认术语 | ~200 条 AI/ML/技术领域术语（中英对照 + 领域标签） |
| 自定义术语 | `POST /api/glossary/upload` — JSON 文件上传 |

### 4.2 新增模块

```
server/rag/
├── __init__.py         # 模块入口，暴露 init_rag() / get_retriever()
├── store.py            # ChromaDB 初始化 + CRUD
├── retriever.py        # Embedding 相似度检索
├── glossary.py         # 内置默认术语表 (~200条)
└── acronyms.py         # 缩写解析字典 (~100条)
```

### 4.3 默认术语表结构

```python
# glossary.py
DEFAULT_GLOSSARY: list[dict] = [
    {
        "en": "transformer",
        "zh": "Transformer 模型",
        "domain": "AI",
    },
    {
        "en": "reinforcement learning from human feedback",
        "zh": "基于人类反馈的强化学习",
        "domain": "AI",
    },
    {
        "en": "attention mechanism",
        "zh": "注意力机制",
        "domain": "AI",
    },
    # ... ~200 entries covering AI, CS, business tech domains
]
```

### 4.4 缩写解析字典

```python
# acronyms.py
ACRONYMS: dict[str, tuple[str, str]] = {
    "RLHF": ("Reinforcement Learning from Human Feedback", "基于人类反馈的强化学习"),
    "LLM": ("Large Language Model", "大语言模型"),
    "RAG": ("Retrieval-Augmented Generation", "检索增强生成"),
    "ASR": ("Automatic Speech Recognition", "自动语音识别"),
    "TTS": ("Text-to-Speech", "语音合成"),
    "GPU": ("Graphics Processing Unit", "图形处理器"),
    # ... ~100 entries
}
```

### 4.5 初始化流程

```python
# store.py
async def init_rag(embedder) -> Retriever:
    """服务启动时调用一次"""
    client = chromadb.PersistentClient(path="server/data/chroma")
    collection = client.get_or_create_collection(
        name="glossary",
        metadata={"hnsw:space": "cosine"},
    )
    # 如果是首次启动，加载默认术语表
    if collection.count() == 0:
        load_default_glossary(collection, embedder)
    return Retriever(collection, embedder)
```

---

## 五、译前检索 + 上下文注入

### 5.1 方案

不在翻译流中途处理 `tool_calls`（复杂度高），改用 **译前检索 + Prompt 注入**：

```
源文本 → 提取术语候选词 → RAG 检索 → 构建术语表文本 → 注入 Prompt → LLM 翻译
```

### 5.2 新增文件

`server/translator/tools.py`：

```python
# 核心接口
async def enrich_context(source_text: str, retriever) -> str:
    """
    从 RAG 检索相关术语，构建术语表注入文本。
    返回空字符串表示无匹配术语。
    """
    # 1. 提取英文候选词 (名词短语、大写缩写)
    candidates = extract_term_candidates(source_text)

    # 2. 缩写词典直接匹配 (O(1), 无 Embedding 开销)
    acronym_matches = resolve_acronyms(source_text)

    # 3. RAG 检索 (Embedding → Chroma)
    rag_matches = retriever.search(candidates, top_k=5, threshold=0.7)

    # 4. 合并去重，构建注入文本
    all_matches = merge_and_dedup(acronym_matches, rag_matches)
    if not all_matches:
        return ""

    return format_glossary_context(all_matches)
    # 返回示例: "参考术语: Transformer → Transformer 模型; RLHF → 基于人类反馈的强化学习"
```

### 5.3 Prompt 修改

`server/translator/prompt.py` — 在现有 SYSTEM_PROMPT 末尾追加注入槽位：

```python
SYSTEM_PROMPT_TEMPLATE = """你是专业英译中同声传译翻译...
... (现有规则不变) ...

{glossary_section}

请翻译以下英文为中文："""

def build_prompt(source_text: str, glossary_context: str) -> str:
    if glossary_context:
        glossary_section = f"[术语参考]\n{glossary_context}\n"
    else:
        glossary_section = ""
    return SYSTEM_PROMPT_TEMPLATE.format(
        glossary_section=glossary_section
    ) + f"\n{source_text}"
```

### 5.4 翻译管线集成

`server/translator/deepseek_provider.py` 修改 `stream_translate`：

```python
async def stream_translate(self, text, context, config):
    # 译前: 检索术语 (非阻塞，失败不影响主流)
    glossary = ""
    if self.retriever:  # RAG 可用
        try:
            glossary = await enrich_context(text, self.retriever)
        except Exception:
            logger.warning("RAG retrieval failed, skipping")

    # 构建 Prompt (含术语注入)
    prompt = build_prompt(text, glossary)

    # 流式翻译 (逻辑不变)
    async for chunk in self._stream_llm(prompt, config):
        yield chunk
```

### 5.5 性能影响

| 环节 | 额外耗时 | 说明 |
|------|---------|------|
| 候选词提取 | ~1ms | 正则 + 简单规则 |
| 缩写匹配 | ~0ms | 字典 O(1) 查找 |
| Embedding 检索 | ~5ms | 本地 MiniLM，向量维度 384 |
| Prompt 拼接 | ~0ms | 纯字符串操作 |
| **总计** | **~6ms** | 对 ~1s 同传延迟几乎无影响 |

---

## 六、API 端点

### 6.1 新增端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/glossary/upload` | POST | 上传自定义术语 JSON |
| `/api/glossary/stats` | GET | 返回术语库统计信息 |
| `/api/glossary/search` | GET | 关键词搜索术语 `?q=transformer` |

### 6.2 请求/响应格式

```json
// POST /api/glossary/upload
// Request body (JSON):
{
  "terms": [
    {"en": "quantization", "zh": "量化", "domain": "AI"}
  ]
}

// Response:
{
  "status": "ok",
  "imported": 1,
  "total": 201
}

// GET /api/glossary/stats
// Response:
{
  "total_terms": 201,
  "domains": {"AI": 120, "CS": 50, "Business": 31}
}

// GET /api/glossary/search?q=transformer&top_k=5
// Response:
{
  "results": [
    {"en": "transformer", "zh": "Transformer 模型", "domain": "AI", "score": 0.95}
  ]
}
```

---

## 七、容错设计

### 7.1 降级链

```
RAG 初始化
  ├── ChromaDB 可用 → 加载默认术语表，建立索引 ✅
  ├── ChromaDB 不可用 → 仅用缩写词典（纯内存，零依赖）⚠️
  └── Embedding 模型未就绪 → 关键词子串匹配降级 ⚠️

翻译时检索
  ├── RAG 命中术语 → 注入 Prompt ✅
  ├── RAG 无匹配 → 跳过注入，正常翻译 ✅
  └── RAG 异常/超时 → 捕获异常，降级为无术语注入 ⚠️
```

### 7.2 核心原则（延续 Phase 1）

- **主链路优先**：DeepSeek 翻译不依赖 RAG，RAG 挂了翻译照跑
- **优雅降级**：Embedding → 关键词 → 缩写词典，层层兜底
- **状态透明**：RAG 初始化状态通过日志输出，API stats 端点可查

---

## 八、文件变更汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `client/public/audio-processor.js` | 新增 | AudioWorklet 处理器 |
| `client/src/hooks/useAudioCapture.ts` | 修改 | AudioWorklet 迁移 |
| `server/rag/__init__.py` | 新增 | RAG 模块入口 |
| `server/rag/store.py` | 新增 | ChromaDB 初始化 + CRUD |
| `server/rag/retriever.py` | 新增 | Embedding 检索接口 |
| `server/rag/glossary.py` | 新增 | 默认术语表 (~200条) |
| `server/rag/acronyms.py` | 新增 | 缩写词典 (~100条) |
| `server/translator/tools.py` | 新增 | 译前检索 + 上下文构建 |
| `server/translator/prompt.py` | 修改 | Prompt 加术语表注入槽位 |
| `server/translator/deepseek_provider.py` | 修改 | 调用 tools.enrich_context |
| `server/main.py` | 修改 | RAG 初始化 + 新增 API |
| `server/requirements.txt` | 修改 | 添加 `chromadb` |
| `server/config.py` | 修改 | 新增 RAG 相关配置项 |
| `server/tests/` (+10 文件) | 新增 | pytest 测试套件 |

---

## 九、实现顺序

1. **AudioWorklet 迁移** — 独立模块，先行完成
2. **RAG 基础设施** — store + retriever + glossary + acronyms（纯数据，无外部依赖）
3. **译前检索集成** — tools.py + prompt.py + deepseek_provider.py
4. **API 端点** — main.py 新增 glossary 路由
5. **测试** — 随模块编写，不另开阶段
6. **端到端验证** — 启动服务，确认翻译带术语注入
