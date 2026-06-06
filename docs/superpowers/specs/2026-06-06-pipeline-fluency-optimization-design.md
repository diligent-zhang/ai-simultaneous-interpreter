# 管道流畅度优化 — 设计文档

> 版本: v1.0 | 日期: 2026-06-06 | 状态: 待实现

## 一、背景

当前 AI 同声传译助手存在四大问题：

1. **字幕碎片化**：每个 partial 翻译追加为新行，屏幕被逐字刷屏
2. **延迟过高**：InterimFilter 保守 + LLM `<<WAIT>>` 双重等待，稳态 3-5s
3. **长句卡顿**：LLM 每个 token 都 yield（30+次/s），React 频繁渲染
4. **TTS 不流畅**：等 final 才朗读 + Edge TTS 串行 fetch 有间隙

## 二、优化目标

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 字幕首字延迟 | 2-5s | ~700ms-1.5s |
| 语音首字延迟 | 4-8s | ~800ms-1.6s |
| 字幕更新频率 | 30+/s (抖动) | ~8-12/s |
| TTS 播放连续性 | 有 audible gap | 无间隙 |

## 三、改动范围

聚焦翻译流畅度 + 初始准确性，修正功能留后优化。

### 后端 (5 files)

#### 1. `server/asr/filter.py` — 过滤器激进化

- 字符阈值 50→20
- 超时 3s→1.5s
- 新增触发条件：检测到 "名词+动词" 即发送（如 "the model uses"）
- 新增：从句引导词检测（that/which/when/if）

#### 2. `server/translator/deepseek_provider.py` — 翻译端节流

- 增量 < 2 中文字符 → 不 yield
- 减少 yield 频率：30+/s → ~8-12/s

#### 3. `server/main.py` — 管道优化

- 翻译 segment_id 固定化，同一次请求的 partial 共用同一 ID
- 消息新增 `replace: bool` 字段，前端据此决定替换/追加
- 翻译去重增强

#### 4. `server/translator/prompt.py` — LLM Prompt 优化

- 移除 `<<WAIT>>` 机制（过滤器已在源头把关）
- 新增："即使输入不完整也请尽力翻译已知部分"

#### 5. `server/config.py`

- `DEEPSEEK_MAX_TOKENS`: 512 → 1024

### 前端 (3 files)

#### 6. `client/src/App.tsx` — 字幕逻辑 + 激进 TTS

- 字幕 updateOrAppend：`replace=true` → 替换同 segment_id；`replace=false` → 追加
- 激进流式 TTS：收到 partial 翻译 ≥5 字即朗读，同 segment 增量 >10 字追加朗读
- 维持修正不重读行为

#### 7. `client/src/SubtitleOverlay.tsx` — 字幕渲染优化

- 新增 SubtitleEntry 字段：`replace`, `sequence`
- partial 行显示闪烁光标指示器
- 去掉每行独立的 fadeIn 动画（partial 替换时反复触发）

#### 8. `client/src/hooks/useTTS.ts` — Edge TTS 预取管线

- 双缓冲：播放 chunk N 时后台 fetch chunk N+1
- AudioBufferSourceNode 精确调度消除间隙（50ms 交叉淡入淡出）
- Browser TTS 保持作为 fallback

### 消息协议变更

```json
// SubtitleMessage 新增字段
{
  "type": "subtitle",
  "segment_id": "trans_0042",
  "text": "人工智能正在重塑",
  "is_final": false,
  "source": "translation",
  "replace": true,       // NEW: true→前端替换同ID旧条目
  "sequence": 3          // NEW: 同segment内序号
}
```

## 四、不改动的部分

- 修正引擎（CorrectionEngine）：保持现有行为，不重读，仅更新字幕
- 修正动画（划线→高亮）：留后续实现
- RAG / Glossary：不变
- ASR (Deepgram)：不变
