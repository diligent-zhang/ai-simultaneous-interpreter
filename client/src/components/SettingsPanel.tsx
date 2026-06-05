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
      position: 'fixed', top: 0, right: 0, width: 300, height: '100vh',
      background: 'rgba(20,20,20,0.95)', color: '#fff', zIndex: 10000,
      padding: 24, overflowY: 'auto', fontFamily: 'system-ui, sans-serif',
      boxShadow: '-4px 0 20px rgba(0,0,0,0.5)',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 18 }}>⚙️ 设置</h2>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', fontSize: 20, cursor: 'pointer' }}>✕</button>
      </div>

      <Section title="显示">
        <Row label="字号">
          <input type="range" min={14} max={36} value={settings.fontSize}
            onChange={e => onUpdate({ fontSize: Number(e.target.value) })} />
          <span style={{ marginLeft: 8, minWidth: 28 }}>{settings.fontSize}px</span>
        </Row>
        <Row label="最大行数">
          <select value={settings.maxLines}
            onChange={e => onUpdate({ maxLines: Number(e.target.value) })}
            style={{ background: '#333', color: '#fff', border: '1px solid #555', borderRadius: 4, padding: '2px 8px' }}>
            <option value={2}>2</option><option value={3}>3</option>
            <option value={5}>5</option><option value={8}>8</option>
          </select>
        </Row>
        <Row label="影院模式">
          <Toggle checked={settings.cinemaMode}
            onChange={v => onUpdate({ cinemaMode: v })} />
        </Row>
      </Section>

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
      <span style={{ width: 80, flexShrink: 0 }}>{label}</span>
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
