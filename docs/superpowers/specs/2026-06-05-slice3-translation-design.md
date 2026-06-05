# Slice 3: DeepSeek 翻译集成 — 设计 + 计划

> 版本: v1.0 | 日期: 2026-06-05

---

## 目标

英文 ASR 结果 → DeepSeek 流式翻译 → 中英双语实时字幕

## 管线

```
PCM → WS → asyncio.Queue → Deepgram ASR → ASRResult
                                              │
                                   ┌──────────┴──────────┐
                                   │  interim → 前端英文草稿  │
                                   │  final → InterimFilter  │
                                   └──────────┬──────────┘
                                              │ (通过过滤)
                                   DeepSeek 流式翻译
                                              │
                                   SubtitleMessage(source="translation")
                                              │
                                   前端双语字幕 (英文小字 + 中文大字)
```

## 文件

```
新增:
server/translator/__init__.py
server/translator/base.py           ← TranslationProvider ABC
server/translator/types.py          ← TranslationConfig, TranslationResult, TranslationContext
server/translator/prompt.py         ← 结构感知翻译 Prompt
server/translator/deepseek_provider.py ← DeepSeek 流式
server/asr/filter.py               ← InterimFilter + 完整性预判
client/src/hooks/useSubtitleFilter.ts ← 前端 subtitle 消息状态管理

修改:
server/config.py                    ← + DeepSeek 配置
server/requirements.txt             ← + openai
server/main.py                      ← ASR → Filter → Translation 管线
client/src/types/messages.ts        ← + TranslationSubtitle 类型
client/src/App.tsx                  ← 双语字幕状态管理
client/src/components/SubtitleOverlay.tsx ← 双语渲染
client/src/components/AudioCapture.tsx   ← 处理 subtitle 消息(非echo)
```

## 非目标

- 不实现修正引擎 (Slice 4)
- 不实现 Function Calling / RAG
- 不实现 OpenAI 备用翻译
