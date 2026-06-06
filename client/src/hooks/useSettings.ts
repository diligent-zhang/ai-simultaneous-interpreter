import { useState, useEffect, useCallback } from 'react';

export interface AppSettings {
  fontSize: number;
  maxLines: number;
  cinemaMode: boolean;
  ttsVolume: number;
  ttsEnabled: boolean;
  correctionEnabled: boolean;
  ttsProvider: 'browser' | 'edge';
  ttsVoice: string;
}

const DEFAULT_SETTINGS: AppSettings = {
  fontSize: 22,
  maxLines: 8,
  cinemaMode: false,
  ttsVolume: 0.8,
  ttsEnabled: true,
  correctionEnabled: true,
  ttsProvider: 'browser',
  ttsVoice: 'zh-CN-XiaoxiaoNeural',
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
