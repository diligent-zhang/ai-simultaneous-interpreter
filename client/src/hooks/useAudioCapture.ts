/**
 * useAudioCapture — 浏览器标签页音频捕获 Hook。
 *
 * 使用 getDisplayMedia API 捕获标签页/system音频，
 * 通过 AudioContext 处理为 PCM 16kHz 16bit mono 格式，
 * 每 40ms 输出一帧。
 */

import { useRef, useCallback, useState } from 'react';

const TARGET_SAMPLE_RATE = 16000;
const FRAME_DURATION_MS = 40; // 40ms/帧

interface UseAudioCaptureOptions {
  onAudioFrame: (pcmData: ArrayBuffer) => void;
}

interface UseAudioCaptureReturn {
  startCapture: () => Promise<void>;
  stopCapture: () => void;
  isCapturing: boolean;
  error: string | null;
}

export function useAudioCapture({
  onAudioFrame,
}: UseAudioCaptureOptions): UseAudioCaptureReturn {
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaStreamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  const stopCapture = useCallback(() => {
    // 停止 ScriptProcessor
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    // 断开音频源
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    // 关闭 AudioContext
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    // 停止 MediaStream 轨道
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    setIsCapturing(false);
    setError(null);
  }, []);

  const startCapture = useCallback(async () => {
    try {
      setError(null);

      // Step 1: 获取显示媒体流（含系统音频）
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true, // Chrome 要求 video 必须为 true
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        } as MediaTrackConstraints,
      });
      mediaStreamRef.current = stream;

      // Step 2: 提取音频轨道
      const audioTrack = stream.getAudioTracks()[0];
      if (!audioTrack) {
        throw new Error('未检测到音频轨道。请确保在浏览器标签页中选择了"分享音频"。');
      }

      // 监听轨道结束（用户停止分享）
      audioTrack.onended = () => {
        stopCapture();
      };

      // 关闭视频轨道（我们只需要音频）
      stream.getVideoTracks().forEach((track) => track.stop());

      // Step 3: 创建 AudioContext + ScriptProcessor 处理管线
      const audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
      audioContextRef.current = audioContext;

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      // ScriptProcessor: 缓冲区大小 = sampleRate * frameDuration / 1000
      const bufferSize = Math.floor(TARGET_SAMPLE_RATE * FRAME_DURATION_MS / 1000);
      const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (event: AudioProcessingEvent) => {
        const inputBuffer = event.inputBuffer;
        const channelData = inputBuffer.getChannelData(0);

        // 转为 16-bit PCM
        const pcmBuffer = new ArrayBuffer(channelData.length * 2);
        const pcmView = new DataView(pcmBuffer);
        for (let i = 0; i < channelData.length; i++) {
          // Float32 [-1, 1] → Int16 [-32768, 32767]
          const sample = Math.max(-1, Math.min(1, channelData[i]));
          pcmView.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
        }

        onAudioFrame(pcmBuffer);
      };

      source.connect(processor);

      // 零增益节点：保持音频图连通（否则 onaudioprocess 不触发），但静音原声
      const silenceGain = audioContext.createGain();
      silenceGain.gain.value = 0;
      processor.connect(silenceGain);
      silenceGain.connect(audioContext.destination);

      setIsCapturing(true);
    } catch (err) {
      const message = err instanceof Error ? err.message : '音频捕获失败';
      setError(message);
      stopCapture();
    }
  }, [onAudioFrame, stopCapture]);

  return { startCapture, stopCapture, isCapturing, error };
}
