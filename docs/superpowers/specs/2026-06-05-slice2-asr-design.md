# Slice 2: ASR 集成 — 设计

> 版本: v1.0 | 日期: 2026-06-05 | 基于设计文档 v1.1

---

## 目标

英文语音 → Deepgram 流式识别 → 前端英文实时字幕

## 架构

```
浏览器 PCM 帧 → WS /ws → asyncio.Queue → Deepgram WS → ASRResult (interim/final)
                              │
浏览器字幕 ← WS /ws ← SubtitleMessage ←───────────────┘
```

## 关键决策

| 问题 | 选择 | 原因 |
|------|------|------|
| Deepgram 连接 | SDK `listen_websocket()` | 官方封装 |
| 音频桥接 | `asyncio.Queue` | 解耦 |
| 并发 | 每客户端一个 `asyncio.create_task` | 简单可控 |
| Interim | 发送（`is_final: false`） | 前端草稿态 |

## 文件

```
新增:
server/asr/__init__.py
server/asr/base.py              ← ASRProvider ABC
server/asr/types.py             ← ASRResult, ASRConfig
server/asr/deepgram_provider.py ← Deepgram 实现

修改:
server/main.py                  ← echo → ASR pipeline
server/requirements.txt          ← + deepgram-sdk
server/config.py                 ← + DEEPGRAM_OPTIONS

前端: 无需改（SubtitleMessage 已有 source/asr 字段）
```

## 非目标

- 不实现 Azure 备用 ASR
- 不翻译，不修正，不 TTS
