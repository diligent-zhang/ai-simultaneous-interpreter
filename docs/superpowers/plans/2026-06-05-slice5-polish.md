# Slice 5: 完善收尾 — 实现计划

> **For agentic workers:** Use superpowers:subagent-driven-development

**Goal:** 设置面板、连接预热、影院模式、状态栏增强、降级切换

---

### Task 1: 设置面板 + useSettings Hook

**Create: client/src/hooks/useSettings.ts**
```typescript
import { useState, useEffect, useCallback } from 'react';

export interface AppSettings {
  fontSize: number;
  maxLines: number;
  cinemaMode: boolean;
  ttsVolume: number;
  ttsEnabled: boolean;
  correctionEnabled: boolean;
  apiKeys: {
    deepgram: string;
    deepseek: string;
  };
}

const DEFAULT_SETTINGS: AppSettings = {
  fontSize: 22,
  maxLines: 8,
  cinemaMode: false,
  ttsVolume: 0.8,
  ttsEnabled: true,
  correctionEnabled: true,
  apiKeys: {
    deepgram: '',
    deepseek: '',
  },
};

function loadSettings(): AppSettings {
  try {
    const saved = localStorage.getItem('ai-interpreter-settings');
    if (saved) return { ...DEFAULT_SETTINGS, ...JSON.parse(saved) };
  } catch {}
  return DEFAULT_SETTINGS;
}

export function useSettings() {
  const [settings, setSettings] = useState<AppSettings>(loadSettings);

  useEffect(() => {
    localStorage.setItem('ai-interpreter-settings', JSON.stringify(settings));
  }, [settings]);

  const update = useCallback((partial: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...partial }));
  }, []);

  return { settings, update };
}
```

**Create: client/src/components/SettingsPanel.tsx**
```tsx
import type { AppSettings } from '../hooks/useSettings';

interface SettingsPanelProps {
  settings: AppSettings;
  onUpdate: (partial: Partial<AppSettings>) => void;
  isOpen: boolean;
  onClose: () => void;
}

export default function SettingsPanel({ settings, onUpdate, isOpen, onClose }: SettingsPanelProps) {
  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed', top: 0, right: 0, width: 320, height: '100vh',
      background: 'rgba(20,20,20,0.95)', color: '#fff', zIndex: 10000,
      padding: 24, overflowY: 'auto', fontFamily: 'system-ui, sans-serif',
      boxShadow: '-4px 0 20px rgba(0,0,0,0.5)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>⚙️ 设置</h2>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', fontSize: 20, cursor: 'pointer' }}>✕</button>
      </div>

      {/* 显示 */}
      <Section title="显示">
        <Row label="字号">
          <input type="range" min={14} max={36} value={settings.fontSize}
            onChange={e => onUpdate({ fontSize: Number(e.target.value) })} />
          <span style={{ marginLeft: 8, minWidth: 28 }}>{settings.fontSize}px</span>
        </Row>
        <Row label="最大行数">
          <select value={settings.maxLines}
            onChange={e => onUpdate({ maxLines: Number(e.target.value) })}>
            <option value={2}>2</option><option value={3}>3</option>
            <option value={5}>5</option><option value={8}>8</option>
          </select>
        </Row>
        <Row label="影院模式">
          <Toggle checked={settings.cinemaMode}
            onChange={v => onUpdate({ cinemaMode: v })} />
        </Row>
      </Section>

      {/* TTS */}
      <Section title="语音">
        <Row label="TTS 朗读">
          <Toggle checked={settings.ttsEnabled}
            onChange={v => onUpdate({ ttsEnabled: v })} />
        </Row>
        <Row label="TTS 音量">
          <input type="range" min={0} max={100} value={Math.round(settings.ttsVolume * 100)}
            onChange={e => onUpdate({ ttsVolume: Number(e.target.value) / 100 })} />
          <span style={{ marginLeft: 8 }}>{Math.round(settings.ttsVolume * 100)}%</span>
        </Row>
      </Section>

      {/* 修正 */}
      <Section title="修正">
        <Row label="启用修正引擎">
          <Toggle checked={settings.correctionEnabled}
            onChange={v => onUpdate({ correctionEnabled: v })} />
        </Row>
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 20 }}>
      <h3 style={{ fontSize: 13, color: '#999', marginBottom: 10, textTransform: 'uppercase' }}>{title}</h3>
      {children}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 10, fontSize: 14 }}>
      <span style={{ width: 90, flexShrink: 0 }}>{label}</span>
      {children}
    </div>
  );
}

function Toggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <button onClick={() => onChange(!checked)} style={{
      width: 48, height: 26, borderRadius: 13, border: 'none',
      background: checked ? '#4caf50' : '#555', cursor: 'pointer',
      position: 'relative', transition: 'background 0.2s',
    }}>
      <span style={{
        position: 'absolute', top: 3, left: checked ? 25 : 3,
        width: 20, height: 20, borderRadius: '50%', background: '#fff',
        transition: 'left 0.2s',
      }} />
    </button>
  );
}
```

---

### Task 2: 连接预热 + 影院模式 + 状态栏

**Files:**
- Modify: `client/src/App.tsx`
- Modify: `client/src/App.css`
- Modify: `client/src/components/SubtitleOverlay.tsx`
- Modify: `client/src/components/AudioCapture.tsx`

**App.tsx changes:**
```tsx
import { useState, useEffect } from 'react';
import AudioCapture from './components/AudioCapture';
import SubtitleOverlay from './components/SubtitleOverlay';
import SettingsPanel from './components/SettingsPanel';
import { onMessage, connect } from './services/websocket';
import { useTTS } from './hooks/useTTS';
import { useSettings } from './hooks/useSettings';
import type { ServerMessage, SubtitleMessage, CorrectionMessage, SubtitleEntry } from './types/messages';
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
        setSubtitles(prev => [...prev, entry].slice(-MAX_SUBTITLES));

        if (settings.ttsEnabled && sub.source === 'translation' && sub.is_final) {
          speak(sub.text);
        }
      } else if (msg.type === 'correction' && settings.correctionEnabled) {
        const corr = msg as CorrectionMessage;
        setSubtitles(prev => prev.map(s =>
          s.id.startsWith(corr.segment_id) ? { ...s, text: corr.new_text } : s
        ));
      } else if (msg.type === 'status') {
        const st = msg as any;
        if (st.latency_ms) setLatencyMs(st.latency_ms);
        if (st.asr_status === 'connected') setAsrProvider('Deepgram');
        if (st.translation_status === 'connected') setTransProvider('DeepSeek');
      }
    });
    return unsub;
  }, [speak, settings.ttsEnabled, settings.correctionEnabled]);

  const maxLines = settings.cinemaMode ? 2 : settings.maxLines;
  const fontSize = settings.cinemaMode ? Math.round(settings.fontSize * 0.8) : settings.fontSize;

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
```

**AudioCapture.tsx — 增强状态栏显示服务商和延迟:**

Replace the status display span with:
```tsx
<span>
  🟢 {asrProvider} · {transProvider}
  {latencyMs > 0 && ` · ${latencyMs}ms`}
</span>
```

And add a settings gear button (⚙️) that calls `onSettingsClick`.

**SubtitleOverlay.tsx — 影院模式:**

When `cinemaMode=true`:
- No animation (correction flash disabled)
- Smaller subtitle background (just text shadow instead of solid bg)
- Only show last `maxLines` entries

Add to props: `cinemaMode: boolean; fontSize: number; maxLines: number;`

**App.css — 影院模式样式:**
```css
.app.cinema-mode {
  background: transparent !important;
}
```

---

### Task 3: 后端降级逻辑

**Modify: server/main.py**

In `run_asr()`, when Deepgram provider fails to connect or throws an error, auto-fallback to echo mode instead of crashing:

```python
# In run_asr, a failed Deepgram connection automatically falls back to:
# "DEEPGRAM_API_KEY not set" path (already implemented)
# Add: catch specific connection errors and fall back
```

Translation: when DeepSeek throws, the error is already caught per-translation. No change needed.

In the status message, include ASR/translation provider status more accurately.

---

### Task 4: 验证 + Commit

- `cd client && npx tsc --noEmit` — zero errors
- `cd server && timeout 5 python main.py 2>&1` — starts clean
- Manual: open browser, see settings panel, cinema mode toggle works
