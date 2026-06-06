/**
 * useTTS — 双路径 TTS 朗读 Hook。
 *
 * Browser 模式: SpeechSynthesis API（现有逻辑）
 * Edge 模式: fetch /api/tts → AudioContext 解码播放
 *
 * 两种模式共用智能分块 + 队列追进度机制。
 */
import { useRef, useCallback } from 'react';

const MAX_CHUNK = 150;
const MAX_QUEUE = 3;

interface TTSOptions {
  provider: 'browser' | 'edge';
  voice?: string;
}

export function useTTS(options?: TTSOptions) {
  const provider = options?.provider ?? 'browser';
  const voice = options?.voice ?? 'zh-CN-XiaoxiaoNeural';

  const queueRef = useRef<string[]>([]);
  const playingRef = useRef(false);
  const audioContextRef = useRef<AudioContext | null>(null);

  const splitAtNaturalBreaks = useCallback(
    (text: string, maxLen: number): string[] => {
      const chunks: string[] = [];
      let start = 0;

      while (start < text.length) {
        if (start + maxLen >= text.length) {
          chunks.push(text.slice(start));
          break;
        }

        const segment = text.slice(start, start + maxLen);
        let lastBreak = -1;
        const regex = /[，；。！？,\n]/g;
        let match: RegExpExecArray | null;

        while ((match = regex.exec(segment)) !== null) {
          lastBreak = match.index;
        }

        if (lastBreak > 0) {
          chunks.push(text.slice(start, start + lastBreak + 1));
          start = start + lastBreak + 1;
        } else {
          chunks.push(segment);
          start = start + maxLen;
        }
      }

      return chunks;
    },
    []
  );

  /** Browser SpeechSynthesis path */
  const speakBrowser = useCallback(
    (chunks: string[]) => {
      const utterances = chunks.map((chunk) => {
        const u = new SpeechSynthesisUtterance(chunk);
        u.lang = 'zh-CN';
        u.rate = 1.1;
        u.volume = 0.8;
        return u;
      });

      let idx = 0;
      const playNext = () => {
        if (idx >= utterances.length) {
          playingRef.current = false;
          return;
        }
        const u = utterances[idx++];
        u.onend = () => playNext();
        u.onerror = () => playNext();
        window.speechSynthesis.speak(u);
      };

      playingRef.current = true;
      playNext();
    },
    []
  );

  /** Edge TTS path — fetch MP3 via API, decode with AudioContext */
  const speakEdge = useCallback(
    async (chunks: string[]) => {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }
      const ctx = audioContextRef.current;

      for (const text of chunks) {
        try {
          const resp = await fetch(
            `/api/tts?text=${encodeURIComponent(text)}&voice=${encodeURIComponent(voice)}&rate=%2B10%25`
          );
          if (!resp.ok) {
            speakBrowser([text]);
            continue;
          }
          const arrayBuffer = await resp.arrayBuffer();
          const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
          const source = ctx.createBufferSource();
          source.buffer = audioBuffer;
          source.connect(ctx.destination);
          source.start();
          await new Promise<void>((resolve) => {
            source.onended = () => resolve();
          });
        } catch {
          speakBrowser([text]);
        }
      }
      playingRef.current = false;
    },
    [voice, speakBrowser]
  );

  const speak = useCallback(
    (text: string) => {
      const chunks = splitAtNaturalBreaks(text, MAX_CHUNK);

      if (queueRef.current.length > MAX_QUEUE) {
        if (provider === 'browser') {
          window.speechSynthesis.cancel();
        }
        queueRef.current = [];
      }

      queueRef.current.push(...chunks);

      if (!playingRef.current) {
        const toPlay = [...queueRef.current];
        queueRef.current = [];
        if (provider === 'edge') {
          speakEdge(toPlay);
        } else {
          speakBrowser(toPlay);
        }
      }
    },
    [splitAtNaturalBreaks, speakBrowser, speakEdge, provider]
  );

  const stop = useCallback(() => {
    if (provider === 'browser') {
      window.speechSynthesis?.cancel();
    }
    queueRef.current = [];
    playingRef.current = false;
  }, [provider]);

  return { speak, stop };
}
