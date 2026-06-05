import { useEffect, useRef } from 'react';
import type { SubtitleEntry } from '../types/messages';

interface SubtitleOverlayProps {
  subtitles: SubtitleEntry[];
  cinemaMode: boolean;
  fontSize: number;
  maxLines: number;
}

export default function SubtitleOverlay({ subtitles, cinemaMode, fontSize, maxLines }: SubtitleOverlayProps) {
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
      {subtitles.slice(-maxLines).map((entry) => (
        <div key={entry.id} style={{
          background: cinemaMode ? 'transparent' : 'rgba(0,0,0,0.75)',
          borderRadius: 8,
          padding: entry.source === 'translation' && !cinemaMode ? '10px 20px' : cinemaMode ? '4px 20px' : '4px 20px',
          animation: cinemaMode ? 'none' : 'fadeIn 0.3s ease-out',
          maxWidth: '100%', textAlign: 'center',
        }}>
          {entry.source === 'asr' ? (
            <div style={{
              color: 'rgba(255,255,255,0.6)', fontSize: Math.round(fontSize * 0.64),
              lineHeight: 1.4,
              fontStyle: entry.isFinal ? 'normal' : 'italic',
              opacity: entry.isFinal ? 0.8 : 0.5,
            }}>
              {entry.text}
            </div>
          ) : (
            <div style={{
              color: '#fff', fontSize, fontWeight: 600, lineHeight: 1.5,
              wordBreak: 'break-word',
              ...(cinemaMode
                ? { textShadow: '0 1px 4px rgba(0,0,0,0.8)' }
                : {}),
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
        @keyframes correctionFlash {
          0% { background: rgba(255, 200, 0, 0.5); }
          100% { background: rgba(0, 0, 0, 0.75); }
        }
      `}</style>
    </div>
  );
}
