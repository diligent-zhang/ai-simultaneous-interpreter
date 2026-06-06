/**
 * useAudioCapture — 浏览器标签页音频捕获 Hook。
 *
 * 使用 getDisplayMedia API 捕获标签页/system音频，
 * 通过 AudioWorkletNode 在独立线程处理为 PCM 16kHz 16bit mono 格式，
 * 每 40ms 输出一帧。
 */

import { useRef, useCallback, useState } from 'react';

const TARGET_SAMPLE_RATE = 16000;

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
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);

  const stopCapture = useCallback(() => {
    // Disconnect AudioWorkletNode
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current.port.onmessage = null;
      workletNodeRef.current = null;
    }
    // Disconnect audio source
    if (sourceRef.current) {
      sourceRef.current.disconnect();
      sourceRef.current = null;
    }
    // Close AudioContext
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    // Stop MediaStream tracks
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

      // Step 1: Get display media stream (with system audio)
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: true,
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        } as MediaTrackConstraints,
      });
      mediaStreamRef.current = stream;

      // Step 2: Extract audio track
      const audioTrack = stream.getAudioTracks()[0];
      if (!audioTrack) {
        throw new Error('未检测到音频轨道。请确保在浏览器标签页中选择了"分享音频"。');
      }

      audioTrack.onended = () => {
        stopCapture();
      };

      // Close video tracks (we only need audio)
      stream.getVideoTracks().forEach((track) => track.stop());

      // Step 3: Create AudioContext + AudioWorkletNode pipeline
      const audioContext = new AudioContext({ sampleRate: TARGET_SAMPLE_RATE });
      audioContextRef.current = audioContext;

      // Load AudioWorklet processor module
      await audioContext.audioWorklet.addModule('/audio-processor.js');

      const source = audioContext.createMediaStreamSource(stream);
      sourceRef.current = source;

      const workletNode = new AudioWorkletNode(audioContext, 'audio-processor');
      workletNodeRef.current = workletNode;

      // Receive PCM buffers from the worklet thread
      workletNode.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        onAudioFrame(event.data);
      };

      // Connect: source → worklet → silence → destination
      const silenceGain = audioContext.createGain();
      silenceGain.gain.value = 0; // Mute original audio playback
      source.connect(workletNode);
      workletNode.connect(silenceGain);
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
