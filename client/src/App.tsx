import { useState, useCallback, useEffect } from 'react';
import AudioCapture from './components/AudioCapture';
import SubtitleOverlay from './components/SubtitleOverlay';
import { onMessage } from './services/websocket';
import { useTTS } from './hooks/useTTS';
import type {
  ServerMessage,
  SubtitleMessage,
  CorrectionMessage,
  SubtitleEntry,
} from './types/messages';
import './App.css';

const MAX_SUBTITLES = 20;

function App() {
  const [subtitles, setSubtitles] = useState<SubtitleEntry[]>([]);
  const [wsStatus, setWsStatus] = useState<string>('disconnected');
  const [isCapturing, setIsCapturing] = useState(false);
  const { speak, stop } = useTTS();

  useEffect(() => {
    const unsub = onMessage((msg: ServerMessage) => {
      if (msg.type === 'subtitle') {
        const sub = msg as SubtitleMessage;
        const entry: SubtitleEntry = {
          id: sub.segment_id + '_' + Date.now(),
          text: sub.text,
          timestamp: sub.timestamp,
          source: sub.source,
          isFinal: sub.is_final,
        };
        setSubtitles((prev) => {
          const next = [...prev, entry];
          return next.slice(-MAX_SUBTITLES);
        });

        // TTS: 翻译 final → 朗读
        if (sub.source === 'translation' && sub.is_final) {
          speak(sub.text);
        }
      } else if (msg.type === 'correction') {
        const corr = msg as CorrectionMessage;
        // 更新已显示的字幕文本（触发修正动画）
        setSubtitles((prev) =>
          prev.map((s) =>
            s.id.startsWith(corr.segment_id)
              ? { ...s, text: corr.new_text, isFinal: true }
              : s
          )
        );
      }
    });
    return unsub;
  }, [speak]);

  const handleMessage = useCallback((_text: string) => {}, []);

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
