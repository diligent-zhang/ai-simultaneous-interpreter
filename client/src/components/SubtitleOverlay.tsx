import { useEffect, useRef } from 'react';
import type { SubtitleEntry } from '../types/messages';

interface SubtitleOverlayProps {
  subtitles: SubtitleEntry[];
}

export default function SubtitleOverlay({ subtitles }: SubtitleOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [subtitles]);

  if (subtitles.length === 0) {
    return (
      <div style={{
        position: 'fixed', bottom: '20%', left: '50%', transform: 'translateX(-50%)',
        color: 'rgba(255,255,255,0.4)', fontSize: 16, fontFamily: 'monospace',
        textAlign: 'center', pointerEvents: 'none',
      }}>
        等待音频捕获...
      </div>
    );
  }

  return (
    <div ref={containerRef} style={{
      position: 'fixed', bottom: '10%', left: '50%', transform: 'translateX(-50%)',
      maxWidth: '80%', maxHeight: '45vh', overflowY: 'auto',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
      pointerEvents: 'none',
    }}>
      {subtitles.slice(-8).map((entry) => (
        <div key={entry.id} style={{
          background: 'rgba(0,0,0,0.75)', borderRadius: 8,
          padding: entry.source === 'translation' ? '10px 20px' : '4px 20px',
          animation: 'fadeIn 0.3s ease-out',
          maxWidth: '100%', textAlign: 'center',
        }}>
          {entry.source === 'asr' ? (
            <div style={{
              color: 'rgba(255,255,255,0.6)', fontSize: 14, lineHeight: 1.4,
              fontStyle: entry.isFinal ? 'normal' : 'italic',
              opacity: entry.isFinal ? 0.8 : 0.5,
            }}>
              {entry.text}
            </div>
          ) : (
            <div style={{
              color: '#fff', fontSize: 22, fontWeight: 600, lineHeight: 1.5,
              wordBreak: 'break-word',
            }}>
              {entry.text}
            </div>
          )}
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
