import { useState, useCallback, useEffect } from 'react';
import AudioCapture from './components/AudioCapture';
import SubtitleOverlay from './components/SubtitleOverlay';
import { onMessage } from './services/websocket';
import type { ServerMessage, SubtitleMessage, SubtitleEntry } from './types/messages';
import './App.css';

const MAX_SUBTITLES = 20;

function App() {
  const [subtitles, setSubtitles] = useState<SubtitleEntry[]>([]);
  const [wsStatus, setWsStatus] = useState<string>('disconnected');
  const [isCapturing, setIsCapturing] = useState(false);

  useEffect(() => {
    const unsub = onMessage((msg: ServerMessage) => {
      if (msg.type === 'subtitle') {
        const sub = msg as SubtitleMessage;
        setSubtitles((prev) => {
          const next = [...prev, {
            id: sub.segment_id + '_' + Date.now(),
            text: sub.text,
            timestamp: sub.timestamp,
            source: sub.source,
            isFinal: sub.is_final,
          }];
          return next.slice(-MAX_SUBTITLES);
        });
      }
    });
    return unsub;
  }, []);

  const handleMessage = useCallback((_text: string) => {
    // Slice 3: subtitles come from WebSocket SubtitleMessage directly
  }, []);

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
