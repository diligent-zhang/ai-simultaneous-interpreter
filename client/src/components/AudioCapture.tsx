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
