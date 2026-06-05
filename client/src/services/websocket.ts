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
