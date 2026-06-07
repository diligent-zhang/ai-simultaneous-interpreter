/**
 * useTTS — 双路径 TTS 朗读 Hook。
 *
 * Browser 模式: SpeechSynthesis API
 * Edge 模式: fetch /api/tts → AudioContext 解码播放（双缓冲预取管线）
 *
 * 支持激进流式朗读：partial 翻译立即朗读，增量追加。
 */
import { useRef, useCallback } from 'react';

const MAX_CHUNK = 150;

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

  /** Edge TTS path — 双缓冲预取管线，消除 chunk 间间隙 */
  const speakEdge = useCallback(
    async (chunks: string[]) => {
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContext();
      }
      const ctx = audioContextRef.current;

      if (chunks.length === 0) return;

      // 预取第一个 chunk
      let prefetchPromise: Promise<AudioBuffer | null> | null = fetchAndDecode(
        chunks[0], voice, ctx
      );

      for (let i = 0; i < chunks.length; i++) {
        // 等待当前 chunk 解码完成
        const audioBuffer = await prefetchPromise;
        // 立即启动下一个 chunk 的预取（管线化）
        prefetchPromise = i + 1 < chunks.length
          ? fetchAndDecode(chunks[i + 1], voice, ctx)
          : null;

        if (!audioBuffer) {
          // Edge TTS 失败 → fallback 到 Browser TTS
          speakBrowser(chunks.slice(i));
          return;
        }

        const source = ctx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(ctx.destination);
        source.start();
        await new Promise<void>((resolve) => {
          source.onended = () => resolve();
        });
      }
      playingRef.current = false;
    },
    [voice, speakBrowser]
  );

  /** 从 Edge TTS API 获取并解码音频 */
  const fetchAndDecode = async (
    text: string, voiceName: string, ctx: AudioContext
  ): Promise<AudioBuffer | null> => {
    try {
      const resp = await fetch(
        `/api/tts?text=${encodeURIComponent(text)}&voice=${encodeURIComponent(voiceName)}&rate=%2B10%25`
      );
      if (!resp.ok) return null;
      const arrayBuffer = await resp.arrayBuffer();
      return await ctx.decodeAudioData(arrayBuffer);
    } catch {
      return null;
    }
  };

  /**
   * 朗读文本。增量去重由调用方（App.tsx）处理。
   * 新内容到达时中断当前朗读，确保实时性。
   */
  const speak = useCallback(
    (text: string, _segmentId?: string) => {
      if (!text || text.length === 0) return;

      // 中断当前朗读，播放最新内容（实时翻译场景）
      if (provider === 'browser') {
        window.speechSynthesis.cancel();
      }
      queueRef.current = [];
      playingRef.current = false;

      const chunks = splitAtNaturalBreaks(text, MAX_CHUNK);

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
