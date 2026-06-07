/**
 * useAudioCapture — 浏览器标签页音频捕获 Hook。
 *
 * 使用 getDisplayMedia API 捕获标签页/system音频+画面，
 * 通过 AudioWorkletNode 在独立线程处理为 PCM 16kHz 16bit mono 格式，
 * 每 40ms 输出一帧。同时暴露 MediaStream 用于视频渲染。
 */

import { useRef, useCallback, useState } from 'react';

const TARGET_SAMPLE_RATE = 16000;

interface UseAudioCaptureOptions {
  onAudioFrame: (pcmData: ArrayBuffer) => void;
}

interface UseAudioCaptureReturn {
  startCapture: () => Promise<MediaStream>;
  stopCapture: () => void;
  isCapturing: boolean;
  error: string | null;
  mediaStream: MediaStream | null;
}

export function useAudioCapture({
  onAudioFrame,
}: UseAudioCaptureOptions): UseAudioCaptureReturn {
  const [isCapturing, setIsCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mediaStream, setMediaStream] = useState<MediaStream | null>(null);

  const audioContextRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  const stopCapture = useCallback(() => {
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current.port.onmessage = null;
      workletNodeRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
    }
    setMediaStream(null);
    setIsCapturing(false);
    setError(null);
  }, [mediaStream]);

  const startCapture = useCallback(async () => {
    try {
      setError(null);

      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        } as MediaTrackConstraints,
      });

      // 保留视频轨道用于页面渲染（不再关闭！）
      setMediaStream(stream);

      const audioTrack = stream.getAudioTracks()[0];
      if (!audioTrack) {
        throw new Error('未检测到音频轨道。请确保在浏览器标签页中选择了"分享音频"。');
      }

      audioTrack.onended = () => {
        stopCapture();
      };

      const audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
      audioContextRef.current = audioContext;

      await audioContext.audioWorklet.addModule('/audio-processor.js');

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      const workletNode = new AudioWorkletNode(audioContext, 'audio-processor');
      workletNodeRef.current = workletNode;

      workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        onAudioFrame(event.data);
      };

      const silenceGain = audioContext.createGain();
      silenceGain.gain.value = 0;
      source.connect(workletNode);
      workletNode.connect(silenceGain);
      silenceGain.connect(audioContext.destination);

      setIsCapturing(true);
      return stream;
    } catch (err) {
      const message = err instanceof Error ? err.message : '音频捕获失败';
      setError(message);
      stopCapture();
      throw err;
    }
  }, [onAudioFrame, stopCapture]);

  return { startCapture, stopCapture, isCapturing, error, mediaStream };
}
