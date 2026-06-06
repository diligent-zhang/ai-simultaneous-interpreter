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
const MAX_QUEUE = 5;

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
  // 跟踪每个 segment 已朗读到的位置（用于增量朗读）
  const segmentSpokenLenRef = useRef<Map<string, number>>(new Map());

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
   * 朗读文本。如果提供了 segmentId，支持增量朗读：
   * 只朗读上次朗读位置之后的新增部分。
   */
  const speak = useCallback(
    (text: string, segmentId?: string) => {
      // 增量朗读：只读新增部分
      if (segmentId) {
        const spokenLen = segmentSpokenLenRef.current.get(segmentId) ?? 0;
        if (text.length <= spokenLen) return;  // 没有新内容
        const newPart = text.slice(spokenLen);
        segmentSpokenLenRef.current.set(segmentId, text.length);
        // 只有新增部分足够长才朗读（≥5 字）
        if (newPart.length < 5) return;
        text = newPart;
      }

      const chunks = splitAtNaturalBreaks(text, MAX_CHUNK);

      // 队列溢出：保留最后 MAX_QUEUE 个 chunk
      if (queueRef.current.length > MAX_QUEUE) {
        if (provider === 'browser') {
          window.speechSynthesis.cancel();
        }
        queueRef.current = queueRef.current.slice(-MAX_QUEUE);
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

  /** 清除指定 segment 的朗读记录（修正时用） */
  const clearSegment = useCallback((segmentId: string) => {
    segmentSpokenLenRef.current.delete(segmentId);
  }, []);

  const stop = useCallback(() => {
    if (provider === 'browser') {
      window.speechSynthesis?.cancel();
    }
    queueRef.current = [];
    playingRef.current = false;
    segmentSpokenLenRef.current.clear();
  }, [provider]);

  return { speak, stop, clearSegment };
}
