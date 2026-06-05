/**
 * useTTS — 浏览器 TTS 朗读 Hook。
 *
 * 智能分块: 在自然断点处分割，每段 ≤150 字。
 * 追进度: 队列 >3 积压 → 跳过中间，直接播最新。
 */
import { useRef, useCallback } from 'react';

const MAX_CHUNK = 150;
const MAX_QUEUE = 3;

export function useTTS() {
  const queueRef = useRef<SpeechSynthesisUtterance[]>([]);
  const speakingRef = useRef(false);

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

  const playNext = useCallback(() => {
    if (queueRef.current.length === 0) {
      speakingRef.current = false;
      return;
    }

    speakingRef.current = true;
    const utterance = queueRef.current.shift()!;

    utterance.onend = () => playNext();
    utterance.onerror = () => playNext();

    window.speechSynthesis.speak(utterance);
  }, []);

  const speak = useCallback(
    (text: string) => {
      if (!window.speechSynthesis) return;

      const chunks = splitAtNaturalBreaks(text, MAX_CHUNK);

      // 追进度: 队列积压超过 MAX_QUEUE → 清空播最新
      if (queueRef.current.length > MAX_QUEUE) {
        window.speechSynthesis.cancel();
        queueRef.current = [];
      }

      for (const chunk of chunks) {
        const utterance = new SpeechSynthesisUtterance(chunk);
        utterance.lang = 'zh-CN';
        utterance.rate = 1.1;
        utterance.volume = 0.8;
        queueRef.current.push(utterance);
      }

      if (!speakingRef.current) {
        playNext();
      }
    },
    [splitAtNaturalBreaks, playNext]
  );

  const stop = useCallback(() => {
    window.speechSynthesis?.cancel();
    queueRef.current = [];
    speakingRef.current = false;
  }, []);

  return { speak, stop };
}
