import { useState, useEffect, useRef } from 'react';
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
  const [capturedStream, setCapturedStream] = useState<MediaStream | null>(null);
  const { settings, update } = useSettings();
  const { speak, stop } = useTTS({
    provider: settings.ttsProvider,
    voice: settings.ttsVoice,
  });

  // 记录每个 translation segment 已朗读到的文本位置
  const ttsSegmentTextRef = useRef<Map<string, string>>(new Map());

  // 连接预热：页面加载即建立 WS
  useEffect(() => {
    connect();
  }, []);

  useEffect(() => {
    const unsub = onMessage((msg: ServerMessage) => {
      if (msg.type === 'subtitle') {
        const sub = msg as SubtitleMessage;
        const entry: SubtitleEntry = {
          id: sub.segment_id,
          text: sub.text,
          timestamp: sub.timestamp,
          source: sub.source,
          isFinal: sub.is_final,
          replace: sub.replace,
          sequence: sub.sequence,
        };

        setSubtitles((prev) => {
          // update-or-append: replace=true 且同 id 存在 → 替换
          if (sub.replace && sub.source === 'translation') {
            const exists = prev.some(
              (s) => s.id === sub.segment_id && s.source === 'translation'
            );
            const next = exists
              ? prev.map((s) =>
                  s.id === sub.segment_id && s.source === 'translation'
                    ? entry
                    : s
                )
              : [...prev, entry];
            return next.slice(-MAX_SUBTITLES);
          }
          // ASR interim → 替换同 id 旧条目
          if (sub.replace && sub.source === 'asr') {
            const exists = prev.some(
              (s) => s.id === sub.segment_id && s.source === 'asr'
            );
            const next = exists
              ? prev.map((s) =>
                  s.id === sub.segment_id && s.source === 'asr' ? entry : s
                )
              : [...prev, entry];
            return next.slice(-MAX_SUBTITLES);
          }
          // final → 追加
          const next = [...prev, entry];
          return next.slice(-MAX_SUBTITLES);
        });

        // ─── 激进流式 TTS ─────────────────────────
        if (settings.ttsEnabled && sub.source === 'translation') {
          const prevText = ttsSegmentTextRef.current.get(sub.segment_id) ?? '';
          // 只朗读新增部分
          if (sub.text.length > prevText.length) {
            const newPart = sub.text.slice(prevText.length);
            // final 或有 2+ 字增量即朗读（中文翻译每次增量很小，降低门槛）
            const isFinal = sub.is_final;
            if (isFinal || newPart.length >= 2) {
              speak(isFinal ? sub.text : newPart, sub.segment_id);
            }
          }
          ttsSegmentTextRef.current.set(sub.segment_id, sub.text);
        }
      } else if (msg.type === 'correction' && settings.correctionEnabled) {
        const corr = msg as CorrectionMessage;
        // 清除该 segment 的 TTS 记录（但已读出的声音不重读）
        // 清除该 segment 的已读记录以便修正后可重新朗读
        ttsSegmentTextRef.current.delete(corr.segment_id);
        // 更新字幕文字
        setSubtitles((prev) =>
          prev.map((s) =>
            s.id === corr.segment_id
              ? { ...s, text: corr.new_text, isFinal: true }
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
  }, [speak, stop, settings.ttsEnabled, settings.correctionEnabled]);

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
        onStreamChange={setCapturedStream}
        asrProvider={asrProvider}
        transProvider={transProvider}
        latencyMs={latencyMs}
        onSettingsClick={() => setSettingsOpen(true)}
      />
      {/* 捕获的画面 */}
      {capturedStream && (
        <video
          ref={(el) => { if (el) el.srcObject = capturedStream; }}
          autoPlay
          muted
          className="captured-video"
        />
      )}

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
