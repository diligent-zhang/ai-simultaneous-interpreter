/**
 * AudioWorklet 处理器 — 在独立音频线程运行。
 * 接收 AudioContext 输入，转换为 PCM 16bit 并通过 MessagePort 发送到主线程。
 */
class AudioProcessor extends AudioWorkletProcessor {
  process(inputs, _outputs, _parameters) {
    const input = inputs[0];
    if (!input || input.length === 0) {
      return true;
    }

    const channelData = input[0]; // Float32Array, 16kHz mono
    if (!channelData || channelData.length === 0) {
      return true;
    }

    // Float32 [-1,1] → Int16 PCM
    const pcmBuffer = new ArrayBuffer(channelData.length * 2);
    const pcmView = new DataView(pcmBuffer);
    for (let i = 0; i < channelData.length; i++) {
      const sample = Math.max(-1, Math.min(1, channelData[i]));
      pcmView.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7FFF, true);
    }

    // Post to main thread (transfer ownership for zero-copy)
    this.port.postMessage(pcmBuffer, [pcmBuffer]);

    return true; // Keep processor alive
  }
}

registerProcessor('audio-processor', AudioProcessor);
