import { useState } from 'react';
import AudioCapture from './components/AudioCapture';
import SubtitleOverlay from './components/SubtitleOverlay';
import './App.css';

interface SubtitleEntry {
  id: string;
  text: string;
  timestamp: number;
}

function App() {
  const [subtitles, setSubtitles] = useState<SubtitleEntry[]>([]);
  const [wsStatus, setWsStatus] = useState<string>('disconnected');
  const [isCapturing, setIsCapturing] = useState(false);

  const handleMessage = (text: string) => {
    const entry: SubtitleEntry = {
      id: crypto.randomUUID(),
      text,
      timestamp: Date.now(),
    };
    setSubtitles((prev) => [...prev.slice(-4), entry]);
  };

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
