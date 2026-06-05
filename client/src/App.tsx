import { useState, useEffect } from 'react';
import AudioCapture from './components/AudioCapture';
import SubtitleOverlay from './components/SubtitleOverlay';
import SettingsPanel from './components/SettingsPanel';
import { onMessage, connect } from './services/websocket';
import { useTTS } from './hooks/useTTS';
import { useSettings } from './hooks/useSettings';
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
  const [wsStatus, setWsStatus] = useState<string>('connecting');
  const [isCapturing, setIsCapturing] = useState(false);
  const [latencyMs, setLatencyMs] = useState(0);
  const [asrProvider, setAsrProvider] = useState('Deepgram');
  const [transProvider, setTransProvider] = useState('DeepSeek');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const { speak } = useTTS();
  const { settings, update } = useSettings();

  // 连接预热：页面加载即建立 WS
  useEffect(() => {
    connect();
  }, []);

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

        if (settings.ttsEnabled && sub.source === 'translation' && sub.is_final) {
          speak(sub.text);
        }
      } else if (msg.type === 'correction' && settings.correctionEnabled) {
        const corr = msg as CorrectionMessage;
        setSubtitles((prev) =>
          prev.map((s) =>
            s.id.startsWith(corr.segment_id)
              ? { ...s, text: corr.new_text }
              : s
          )
        );
      } else if (msg.type === 'status') {
        const st = msg as any;
        if (st.latency_ms) setLatencyMs(st.latency_ms);
        if (st.asr_status === 'connected') setAsrProvider('Deepgram');
        else if (st.asr_status === 'error') setAsrProvider('Echo');
        if (st.translation_status === 'connected') setTransProvider('DeepSeek');
        else if (st.translation_status === 'error') setTransProvider('--');
      }
    });
    return unsub;
  }, [speak, settings.ttsEnabled, settings.correctionEnabled]);

  const maxLines = settings.cinemaMode ? 2 : settings.maxLines;
  const fontSize = settings.cinemaMode
    ? Math.round(settings.fontSize * 0.8)
    : settings.fontSize;

  return (
    <div className={`app ${settings.cinemaMode ? 'cinema-mode' : ''}`}>
      <AudioCapture
        wsStatus={wsStatus}
        setWsStatus={setWsStatus}
        isCapturing={isCapturing}
        setIsCapturing={setIsCapturing}
        onMessage={() => {}}
        asrProvider={asrProvider}
        transProvider={transProvider}
        latencyMs={latencyMs}
        onSettingsClick={() => setSettingsOpen(true)}
      />
      <SubtitleOverlay
        subtitles={subtitles}
        cinemaMode={settings.cinemaMode}
        fontSize={fontSize}
        maxLines={maxLines}
      />
      <SettingsPanel
        settings={settings}
        onUpdate={update}
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
      />
    </div>
  );
}

export default App;
