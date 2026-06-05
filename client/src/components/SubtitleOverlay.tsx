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
