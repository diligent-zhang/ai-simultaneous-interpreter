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

  // 去重：同一 id 只保留最后一条（处理 replace 语义）
  const visible = dedupeSubtitles(subtitles).slice(-maxLines);

  return (
    <div ref={containerRef} style={{
      position: 'fixed', bottom: '10%', left: '50%', transform: 'translateX(-50%)',
      maxWidth: '80%', maxHeight: '45vh', overflowY: 'auto',
      display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6,
      pointerEvents: 'none',
    }}>
      {visible.map((entry) => {
        const isPartialTranslation = entry.source === 'translation' && !entry.isFinal;
        return (
          <div key={entry.id} style={{
            background: cinemaMode ? 'transparent' : 'rgba(0,0,0,0.75)',
            borderRadius: 8,
            padding: entry.source === 'translation' && !cinemaMode ? '10px 20px' : cinemaMode ? '4px 20px' : '4px 20px',
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
                {isPartialTranslation && (
                  <span className="cursor-blink" style={{
                    display: 'inline-block', width: 2, height: '1em',
                    background: '#fff', marginLeft: 2, verticalAlign: 'text-bottom',
                  }} />
                )}
              </div>
            )}
          </div>
        );
      })}
      <style>{`
        @keyframes cursorBlink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .cursor-blink {
          animation: cursorBlink 0.6s ease-in-out infinite;
        }
      `}</style>
    </div>
  );
}

/**
 * 字幕去重：同 id → 保留最后一条（实现 replace 语义）
 * isFinal=true 的条目锁定，不再被后续同 id partial 替换
 */
function dedupeSubtitles(entries: SubtitleEntry[]): SubtitleEntry[] {
  const map = new Map<string, SubtitleEntry>();
  // 先记录所有 locked (final) 条目
  for (const e of entries) {
    if (e.isFinal && e.source === 'translation') {
      map.set(e.id, e);
    }
  }
  // 后遍历的会覆盖，但 locked 条目不会被非 final 覆盖
  for (const e of entries) {
    const existing = map.get(e.id);
    if (existing && existing.isFinal && existing.source === 'translation') {
      // 已锁定的 final 翻译不被 partial 覆盖
      if (e.isFinal || e.source !== 'translation') {
        map.set(e.id, e);
      }
      continue;
    }
    map.set(e.id, e);
  }
  // 按时间戳排序
  return Array.from(map.values()).sort((a, b) => a.timestamp - b.timestamp);
}
