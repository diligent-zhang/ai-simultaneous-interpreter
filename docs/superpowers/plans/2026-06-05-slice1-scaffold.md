# Slice 1: 项目脚手架 + 连通性验证 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建后端 FastAPI + 前端 React 项目骨架，实现 WebSocket 连通、TabCapture 音频捕获、简易字幕浮层。

**Architecture:** 单一 WebSocket 连接贯穿全链路——浏览器端捕获标签页音频，通过 WebSocket 发送 PCM 帧到后端，后端接收并回显确认消息，前端展示回显结果在字幕浮层上。

**Tech Stack:** Python 3.11+ / FastAPI / WebSocket | React 18+ / TypeScript / Vite | getDisplayMedia (浏览器 API)

---

## 文件结构总览

```
server/                          # 后端
├── requirements.txt
├── main.py                      # FastAPI 入口 + WebSocket 端点
├── config.py                    # 配置管理
└── models/
    ├── __init__.py
    └── messages.py              # WebSocket 消息协议 (Pydantic)

client/                          # 前端
├── package.json
├── tsconfig.json
├── tsconfig.app.json
├── tsconfig.node.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── App.css
    ├── index.css
    ├── types/
    │   └── messages.ts          # 消息类型定义
    ├── services/
    │   └── websocket.ts         # WebSocket 客户端单例
    ├── hooks/
    │   └── useAudioCapture.ts   # 音频捕获 Hook
    └── components/
        ├── AudioCapture.tsx     # 音频源选择 + 捕获控制
        └── SubtitleOverlay.tsx  # 简易字幕浮层
```

---

### Task 1: 后端项目骨架 (FastAPI + WebSocket 端点)

**Files:**
- Create: `server/requirements.txt`
- Create: `server/config.py`
- Create: `server/models/__init__.py`
- Create: `server/models/messages.py`
- Create: `server/main.py`

- [ ] **Step 1: 创建 requirements.txt**

```txt
fastapi==0.115.6
uvicorn[standard]==0.34.0
websockets==14.1
pydantic==2.10.5
python-dotenv==1.0.1
```

- [ ] **Step 2: 创建 config.py**

```python
"""应用配置管理，从环境变量和 .env 文件加载。"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """全局配置单例。"""

    # 服务
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Deepgram (Slice 2 用)
    DEEPGRAM_API_KEY: str = os.getenv("DEEPGRAM_API_KEY", "")

    # DeepSeek (Slice 3 用)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
    )

    # OpenAI 备用 (Slice 5 用)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # Azure 备用 (Slice 5 用)
    AZURE_SPEECH_KEY: str = os.getenv("AZURE_SPEECH_KEY", "")
    AZURE_SPEECH_REGION: str = os.getenv("AZURE_SPEECH_REGION", "")

    # 修正引擎
    CORRECTION_ENABLED: bool = os.getenv("CORRECTION_ENABLED", "true").lower() == "true"
    MAX_CORRECTION_CALLS: int = int(os.getenv("MAX_CORRECTION_CALLS", "20"))


settings = Settings()
```

- [ ] **Step 3: 创建 models/__init__.py**

```python
"""消息模型包。"""
```

- [ ] **Step 4: 创建 models/messages.py** — WebSocket 消息协议定义

```python
"""WebSocket 消息协议定义。使用 Pydantic 模型确保类型安全。"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ─── 客户端 → 服务端 ───────────────────────────────────

class ClientMessageType(str, Enum):
    """客户端发送的消息类型。"""
    CONFIG = "config"
    PING = "ping"


class ConfigMessage(BaseModel):
    """配置消息：设置语言、服务商偏好等。"""
    type: str = ClientMessageType.CONFIG
    source_lang: str = "en"
    target_lang: str = "zh"
    asr_provider: str = "deepgram"
    translation_provider: str = "deepseek"


class PingMessage(BaseModel):
    """心跳消息。"""
    type: str = ClientMessageType.PING


# ─── 服务端 → 客户端 ───────────────────────────────────

class ServerMessageType(str, Enum):
    """服务端发送的消息类型。"""
    SUBTITLE = "subtitle"
    STATUS = "status"
    PONG = "pong"
    ECHO = "echo"  # Slice 1 专用：连通性验证回显


class SubtitleMessage(BaseModel):
    """字幕消息：包含 ASR 识别或翻译结果。"""
    type: str = ServerMessageType.SUBTITLE
    segment_id: str = Field(description="句段唯一标识")
    text: str
    is_final: bool = False
    source: str = "asr"  # "asr" | "translation"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    timestamp: float = Field(default=0.0)


class StatusMessage(BaseModel):
    """状态消息：当前服务商和延迟信息。"""
    type: str = ServerMessageType.STATUS
    asr_status: str = "idle"  # "idle" | "connected" | "error"
    translation_status: str = "idle"  # "idle" | "connected" | "error"
    latency_ms: int = 0


class PongMessage(BaseModel):
    """心跳响应。"""
    type: str = ServerMessageType.PONG


class EchoMessage(BaseModel):
    """连通性验证回显 (Slice 1 专用)。"""
    type: str = ServerMessageType.ECHO
    original_size: int = 0
    message: str = "audio frame received"
```

- [ ] **Step 5: 创建 main.py** — FastAPI 入口 + WebSocket 端点

```python
"""AI 同声传译助手 — 后端入口。

Slice 1: 基础 WebSocket 连通性验证。
接收音频帧，回显确认消息。
"""

import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from models.messages import EchoMessage, PongMessage

app = FastAPI(
    title="AI Simultaneous Interpreter",
    version="0.1.0",
    description="AI 同声传译助手后端服务",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """健康检查端点。"""
    return {"status": "ok", "version": "0.1.0"}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """主 WebSocket 端点。

    支持:
    - 二进制音频帧 (PCM 16kHz 16bit mono)
    - JSON 控制消息 (config, ping)
    """
    await ws.accept()
    print(f"[WS] Client connected")

    try:
        while True:
            # 接收消息：二进制（音频帧）或文本（JSON 控制消息）
            data = await ws.receive()

            if "bytes" in data:
                # 二进制音频帧 → 回显确认
                audio_bytes = data["bytes"]
                echo = EchoMessage(
                    original_size=len(audio_bytes),
                    message=f"audio frame received: {len(audio_bytes)} bytes",
                )
                await ws.send_json(echo.model_dump())

            elif "text" in data:
                # JSON 控制消息
                import json
                msg = json.loads(data["text"])
                msg_type = msg.get("type", "")

                if msg_type == "ping":
                    pong = PongMessage()
                    await ws.send_json(pong.model_dump())

                elif msg_type == "config":
                    # Slice 1 仅打印配置，后续切片使用
                    print(f"[WS] Config received: {msg}")
                    status = {
                        "type": "status",
                        "asr_status": "idle",
                        "translation_status": "idle",
                        "latency_ms": 0,
                    }
                    await ws.send_json(status)

    except WebSocketDisconnect:
        print(f"[WS] Client disconnected")
    except Exception as e:
        print(f"[WS] Error: {e}")
        await ws.close(code=1011, reason=str(e))


def main():
    """启动服务。"""
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True,
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 安装依赖并验证启动**

```bash
cd server && pip install -r requirements.txt && python main.py
```

Expected: `Uvicorn running on http://0.0.0.0:8000`

- [ ] **Step 7: 测试健康检查端点**

```bash
curl http://localhost:8000/health
```

Expected: `{"status":"ok","version":"0.1.0"}`

- [ ] **Step 8: Commit**

```bash
git add server/ && git commit -m "feat(slice1): add backend scaffold with FastAPI + WebSocket endpoint"
```

---

### Task 2: 前端项目骨架 (Vite + React + TypeScript)

**Files:**
- Create: `client/` 整个项目 (使用 Vite 脚手架)
- Create: `client/src/types/messages.ts`
- Modify: `client/src/App.tsx`
- Modify: `client/src/App.css`
- Create: `client/src/index.css`

- [ ] **Step 1: 使用 Vite 脚手架创建项目**

```bash
cd "c:\Study\简历项目\ai同声传译助手" && npm create vite@latest client -- --template react-ts
```

Expected: `Scaffolding project in .../client... Done.`

- [ ] **Step 2: 安装依赖**

```bash
cd client && npm install
```

- [ ] **Step 3: 创建 types/messages.ts** — 前端消息类型定义

```typescript
// 消息类型定义，与后端 models/messages.py 保持同步

// ─── 客户端 → 服务端 ───────────────────────────────────

export interface ConfigMessage {
  type: 'config';
  source_lang: string;
  target_lang: string;
  asr_provider: string;
  translation_provider: string;
}

export interface PingMessage {
  type: 'ping';
}

export type ClientMessage = ConfigMessage | PingMessage;

// ─── 服务端 → 客户端 ───────────────────────────────────

export interface SubtitleMessage {
  type: 'subtitle';
  segment_id: string;
  text: string;
  is_final: boolean;
  source: 'asr' | 'translation';
  confidence: number;
  timestamp: number;
}

export interface StatusMessage {
  type: 'status';
  asr_status: 'idle' | 'connected' | 'error';
  translation_status: 'idle' | 'connected' | 'error';
  latency_ms: number;
}

export interface PongMessage {
  type: 'pong';
}

export interface EchoMessage {
  type: 'echo';
  original_size: number;
  message: string;
}

export type ServerMessage =
  | SubtitleMessage
  | StatusMessage
  | PongMessage
  | EchoMessage;
```

- [ ] **Step 4: 创建 index.css** — 全局面板样式（字幕浮层基础）

```css
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body, #root {
  width: 100%;
  height: 100%;
  font-family: 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
  background: transparent;
  overflow: hidden;
}
```

- [ ] **Step 5: 修改 App.css** — 应用级布局样式

```css
.app {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  pointer-events: none; /* 允许点击穿透到下方内容 */
}

.app > * {
  pointer-events: auto; /* 子组件恢复可交互 */
}
```

- [ ] **Step 6: 修改 App.tsx** — 应用根组件

```tsx
import { useState } from 'react';
import AudioCapture from './components/AudioCapture';
import SubtitleOverlay from './components/SubtitleOverlay';
import './App.css';

interface SubtitleEntry {
  id: string;
  text: string;
  timestamp: number;
}

function App() {
  const [subtitles, setSubtitles] = useState<SubtitleEntry[]>([]);
  const [wsStatus, setWsStatus] = useState<string>('disconnected');
  const [isCapturing, setIsCapturing] = useState(false);

  const handleMessage = (text: string) => {
    const entry: SubtitleEntry = {
      id: crypto.randomUUID(),
      text,
      timestamp: Date.now(),
    };
    setSubtitles((prev) => [...prev.slice(-4), entry]);
  };

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

- [ ] **Step 7: Commit**

```bash
git add client/ && git commit -m "feat(slice1): add frontend scaffold with Vite + React + TypeScript"
```

---

### Task 3: WebSocket 客户端单例

**Files:**
- Create: `client/src/services/websocket.ts`

- [ ] **Step 1: 创建 services/websocket.ts** — WebSocket 客户端单例

```typescript
/**
 * WebSocket 客户端单例。
 *
 * 职责:
 * - 管理与后端的单一 WS 连接
 * - 支持发送 JSON 消息和二进制音频帧
 * - 自动重连（指数退避）
 * - 消息分发（通过回调注册）
 */

import type { ClientMessage, ServerMessage } from '../types/messages';

export type MessageHandler = (msg: ServerMessage) => void;
export type StatusHandler = (status: string) => void;

const WS_URL = 'ws://localhost:8000/ws';
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;
const HEARTBEAT_INTERVAL_MS = 30000;

let ws: WebSocket | null = null;
let reconnectAttempt = 0;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let messageHandlers: MessageHandler[] = [];
let statusHandlers: StatusHandler[] = [];

function notifyStatus(status: string): void {
  statusHandlers.forEach((fn) => fn(status));
}

function notifyMessage(msg: ServerMessage): void {
  messageHandlers.forEach((fn) => fn(msg));
}

function startHeartbeat(): void {
  stopHeartbeat();
  heartbeatTimer = setInterval(() => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'ping' }));
    }
  }, HEARTBEAT_INTERVAL_MS);
}

function stopHeartbeat(): void {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function scheduleReconnect(): void {
  const delay = Math.min(
    RECONNECT_BASE_MS * 2 ** reconnectAttempt,
    RECONNECT_MAX_MS
  );
  reconnectAttempt++;
  notifyStatus('reconnecting');
  setTimeout(connect, delay);
}

export function connect(): void {
  if (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) {
    return;
  }

  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    reconnectAttempt = 0;
    notifyStatus('connected');
    startHeartbeat();
    console.log('[WS] Connected');
  };

  ws.onmessage = (event: MessageEvent) => {
    try {
      const msg: ServerMessage = JSON.parse(event.data as string);
      notifyMessage(msg);
    } catch {
      // 二进制消息忽略 (服务端不向客户端发二进制)
    }
  };

  ws.onclose = (event: CloseEvent) => {
    stopHeartbeat();
    notifyStatus('disconnected');
    console.log(`[WS] Disconnected: ${event.code} ${event.reason}`);
    if (event.code !== 1000) {
      scheduleReconnect();
    }
  };

  ws.onerror = () => {
    // onclose 会跟随触发，此处只记录
    console.error('[WS] Error');
  };
}

export function disconnect(): void {
  stopHeartbeat();
  reconnectAttempt = 0;
  if (ws) {
    ws.close(1000, 'Client disconnect');
    ws = null;
  }
  notifyStatus('disconnected');
}

export function sendMessage(msg: ClientMessage): void {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
  }
}

export function sendAudioFrame(data: ArrayBuffer): void {
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(data);
  }
}

export function onMessage(handler: MessageHandler): () => void {
  messageHandlers.push(handler);
  return () => {
    messageHandlers = messageHandlers.filter((h) => h !== handler);
  };
}

export function onStatus(handler: StatusHandler): () => void {
  statusHandlers.push(handler);
  return () => {
    statusHandlers = statusHandlers.filter((h) => h !== handler);
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add client/src/services/websocket.ts && git commit -m "feat(slice1): add WebSocket client singleton with reconnect & heartbeat"
```

---

### Task 4: 音频捕获 Hook + 组件

**Files:**
- Create: `client/src/hooks/useAudioCapture.ts`
- Create: `client/src/components/AudioCapture.tsx`

- [ ] **Step 1: 创建 hooks/useAudioCapture.ts** — 音频捕获 Hook

```typescript
/**
 * useAudioCapture — 浏览器标签页音频捕获 Hook。
 *
 * 使用 getDisplayMedia API 捕获标签页/system音频，
 * 通过 AudioContext 处理为 PCM 16kHz 16bit mono 格式，
 * 每 40ms 输出一帧。
 */

import { useRef, useCallback, useState } from 'react';

const TARGET_SAMPLE_RATE = 16000;
const FRAME_DURATION_MS = 40; // 40ms/帧

interface UseAudioCaptureOptions {
  onAudioFrame: (pcmData: ArrayBuffer) => void;
}

interface UseAudioCaptureReturn {
  startCapture: () => Promise<void>;
  stopCapture: () => void;
  isCapturing: boolean;
  error: string | null;
}

export function useAudioCapture({
  onAudioFrame,
}: UseAudioCaptureOptions): UseAudioCaptureReturn {
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  const stopCapture = useCallback(() => {
    // 停止 ScriptProcessor
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    // 断开音频源
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    // 关闭 AudioContext
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    // 停止 MediaStream 轨道
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    setIsCapturing(false);
    setError(null);
  }, []);

  const startCapture = useCallback(async () => {
    try {
      setError(null);

      // Step 1: 获取显示媒体流（含系统音频）
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true, // Chrome 要求 video 必须为 true
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        } as MediaTrackConstraints,
      });
      mediaStreamRef.current = stream;

      // Step 2: 提取音频轨道
      const audioTrack = stream.getAudioTracks()[0];
      if (!audioTrack) {
        throw new Error('未检测到音频轨道。请确保在浏览器标签页中选择了"分享音频"。');
      }

      // 监听轨道结束（用户停止分享）
      audioTrack.onended = () => {
        stopCapture();
      };

      // 关闭视频轨道（我们只需要音频）
      stream.getVideoTracks().forEach((track) => track.stop());

      // Step 3: 创建 AudioContext + ScriptProcessor 处理管线
      const audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      // ScriptProcessor: 缓冲区大小 = sampleRate * frameDuration / 1000
      const bufferSize = Math.floor(TARGET_SAMPLE_RATE * FRAME_DURATION_MS / 1000);
      const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (event: AudioProcessingEvent) => {
        const inputBuffer = event.inputBuffer;
        const channelData = inputBuffer.getChannelData(0);

        // 转为 16-bit PCM
        const pcmBuffer = new ArrayBuffer(channelData.length * 2);
        const pcmView = new DataView(pcmBuffer);
        for (let i = 0; i < channelData.length; i++) {
          // Float32 [-1, 1] → Int16 [-32768, 32767]
          const sample = Math.max(-1, Math.min(1, channelData[i]));
          pcmView.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
        }

        onAudioFrame(pcmBuffer);
      };

      source.connect(processor);
      processor.connect(audioContext.destination); // 连接到输出，否则不触发 onaudioprocess

      setIsCapturing(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : '音频捕获失败';
      setError(message);
      stopCapture();
    }
  }, [onAudioFrame, stopCapture]);

  return { startCapture, stopCapture, isCapturing, error };
}
```

- [ ] **Step 2: 创建 components/AudioCapture.tsx** — 捕获控制组件

```tsx
/**
 * AudioCapture — 音频捕获控制组件。
 *
 * 提供"开始捕获"按钮，将捕获的 PCM 帧通过 WebSocket 发送。
 * 显示连接状态和捕获错误。
 */

import { useCallback, useEffect } from 'react';
import { useAudioCapture } from '../hooks/useAudioCapture';
import { connect, disconnect, sendAudioFrame, sendMessage, onMessage, onStatus } from '../services/websocket';
import type { EchoMessage, ServerMessage } from '../types/messages';

interface AudioCaptureProps {
  wsStatus: string;
  setWsStatus: (status: string) => void;
  isCapturing: boolean;
  setIsCapturing: (capturing: boolean) => void;
  onMessage: (text: string) => void;
}

export default function AudioCapture({
  wsStatus,
  setWsStatus,
  isCapturing,
  setIsCapturing,
  onMessage,
}: AudioCaptureProps) {
  // ─── 处理服务端回显消息 ───────────────────────
  const handleServerMessage = useCallback(
    (msg: ServerMessage) => {
      if (msg.type === 'echo') {
        const echo = msg as EchoMessage;
        onMessage(`📡 ${echo.message}`);
      }
    },
    [onMessage]
  );

  // ─── 注册 WS 消息/状态监听 ───────────────────────
  useEffect(() => {
    const unsubMsg = onMessage(handleServerMessage);
    const unsubStatus = onStatus(setWsStatus);
    return () => {
      unsubMsg();
      unsubStatus();
    };
  }, [handleServerMessage, setWsStatus]);

  // ─── 音频帧发送 ─────────────────────────────
  const handleAudioFrame = useCallback(
    (pcmData: ArrayBuffer) => {
      sendAudioFrame(pcmData);
    },
    []
  );

  const { startCapture, stopCapture, error } = useAudioCapture({
    onAudioFrame: handleAudioFrame,
  });

  // 同步捕获状态到父组件
  useEffect(() => {
    setIsCapturing(isCapturing);
  }, [isCapturing, setIsCapturing]);

  // ─── 开始/停止捕获 ─────────────────────────
  const handleStart = useCallback(async () => {
    connect();
    await startCapture();
  }, [startCapture]);

  const handleStop = useCallback(() => {
    stopCapture();
    disconnect();
  }, [stopCapture]);

  const statusColor =
    wsStatus === 'connected' ? '#4caf50' :
    wsStatus === 'reconnecting' ? '#ff9800' :
    '#f44336';

  return (
    <div style={{
      position: 'fixed',
      top: 12,
      right: 12,
      zIndex: 9999,
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      background: 'rgba(0,0,0,0.75)',
      borderRadius: 8,
      padding: '8px 16px',
      color: '#fff',
      fontSize: 13,
      fontFamily: 'monospace',
    }}>
      <span style={{
        width: 8,
        height: 8,
        borderRadius: '50%',
        background: statusColor,
        display: 'inline-block',
      }} />
      <span>{wsStatus}</span>
      {error && <span style={{ color: '#f44336', marginLeft: 8 }}>{error}</span>}
      {!isCapturing ? (
        <button
          onClick={handleStart}
          style={{
            padding: '4px 12px',
            borderRadius: 4,
            border: '1px solid #4caf50',
            background: 'transparent',
            color: '#4caf50',
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          开始捕获
        </button>
      ) : (
        <button
          onClick={handleStop}
          style={{
            padding: '4px 12px',
            borderRadius: 4,
            border: '1px solid #f44336',
            background: 'transparent',
            color: '#f44336',
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          停止
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add client/src/hooks/useAudioCapture.ts client/src/components/AudioCapture.tsx && git commit -m "feat(slice1): add TabCapture audio capture hook & control component"
```

---

### Task 5: 简易字幕浮层

**Files:**
- Create: `client/src/components/SubtitleOverlay.tsx`

- [ ] **Step 1: 创建 components/SubtitleOverlay.tsx**

```tsx
/**
 * SubtitleOverlay — 简易字幕浮层组件。
 *
 * Slice 1: 仅展示 WebSocket 回显消息，验证连通性。
 * 后续切片会扩展为真正的双语字幕渲染。
 */

import { useEffect, useRef } from 'react';

interface SubtitleEntry {
  id: string;
  text: string;
  timestamp: number;
}

interface SubtitleOverlayProps {
  subtitles: SubtitleEntry[];
}

export default function SubtitleOverlay({ subtitles }: SubtitleOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  // 自动滚动到最新字幕
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [subtitles]);

  if (subtitles.length === 0) {
    return (
      <div style={{
        position: 'fixed',
        bottom: '20%',
        left: '50%',
        transform: 'translateX(-50%)',
        color: 'rgba(255,255,255,0.4)',
        fontSize: 16,
        fontFamily: 'monospace',
        textAlign: 'center',
        pointerEvents: 'none',
      }}>
        等待音频捕获...
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      style={{
        position: 'fixed',
        bottom: '10%',
        left: '50%',
        transform: 'translateX(-50%)',
        maxWidth: '80%',
        maxHeight: '40vh',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
        pointerEvents: 'none',
      }}
    >
      {subtitles.map((entry) => (
        <div
          key={entry.id}
          style={{
            background: 'rgba(0,0,0,0.75)',
            color: '#fff',
            padding: '8px 20px',
            borderRadius: 8,
            fontSize: 18,
            lineHeight: 1.5,
            textAlign: 'center',
            animation: 'fadeIn 0.3s ease-out',
            maxWidth: '100%',
            wordBreak: 'break-word',
          }}
        >
          {entry.text}
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

- [ ] **Step 2: Commit**

```bash
git add client/src/components/SubtitleOverlay.tsx && git commit -m "feat(slice1): add simple subtitle overlay component"
```

---

### Task 6: 修正 main.tsx 入口 + 端到端验证

**Files:**
- Modify: `client/src/main.tsx` (确保入口正确)
- Create: `server/.env.example`

- [ ] **Step 1: 检查并修正 main.tsx**

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

> 注：Vite 脚手架生成的 main.tsx 基本无需修改，只需确认 `index.css` 导入在 App 之前。

- [ ] **Step 2: 创建 .env.example** (后端配置模板)

```bash
# AI 同声传译助手 — 环境变量模板
# 复制此文件为 .env 并填入实际值

HOST=0.0.0.0
PORT=8000

# Deepgram (流式 ASR)
DEEPGRAM_API_KEY=

# DeepSeek (翻译)
DEEPSEEK_API_KEY=

# OpenAI (备用翻译)
OPENAI_API_KEY=

# Azure Speech (备用 ASR)
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=

# 修正引擎
CORRECTION_ENABLED=true
MAX_CORRECTION_CALLS=20
```

- [ ] **Step 3: 启动后端**

```bash
cd server && python main.py
```

Expected: `Uvicorn running on http://0.0.0.0:8000`

- [ ] **Step 4: 启动前端**

```bash
cd client && npm run dev
```

Expected: `VITE vX.X.X ready in XXXms → http://localhost:5173/`

- [ ] **Step 5: 手动端到端验证**

1. 打开浏览器 `http://localhost:5173`
2. 看到 "等待音频捕获..." 占位文字
3. 点击右上角 "开始捕获" 按钮
4. 选择浏览器标签页（勾选"分享音频"）
5. 观察状态灯是否变绿（connected）
6. 观察字幕区域是否出现回显消息：`📡 audio frame received: 640 bytes`

- [ ] **Step 6: Commit**

```bash
git add client/src/main.tsx server/.env.example && git commit -m "feat(slice1): add .env.example, finalize slice 1 integration"
```

---

## 自检清单

- [x] 后端 6 个文件，前端 8 个文件
- [x] 每个 Task 产出可独立提交的代码
- [x] Slice 1 不依赖任何外部 API（Deepgram/DeepSeek）
- [x] WebSocket 协议消息类型前后端一致
- [x] 音频格式统一为 PCM 16kHz 16bit mono
- [x] 无 TBD/TODO/占位符
