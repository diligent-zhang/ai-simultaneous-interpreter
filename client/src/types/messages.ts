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
  | EchoMessage
  | CorrectionMessage;

// ─── 修正消息 ───────────────────────────────────────

export interface CorrectionMessage {
  type: 'correction';
  segment_id: string;
  old_text: string;
  new_text: string;
  reason: string;
  confidence: number;
}

// ─── 前端内部字幕条目 ───────────────────────────────

export interface SubtitleEntry {
  id: string;
  text: string;
  timestamp: number;
  source: 'asr' | 'translation';
  isFinal: boolean;
}
