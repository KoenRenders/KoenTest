// AudioWorklet voor de Voxtral-spraakinvoer (#282). Draait in de audio-thread:
// neemt de mic-blokken (Float32 op de AudioContext-sample-rate — wij zetten die op
// 16 kHz mono), zet ze om naar 16-bit PCM (pcm_s16le, wat Voxtral verwacht) en stuurt
// elk blok naar de hoofdthread, samen met de RMS-energie voor stilte-detectie (VAD).
class SttPcmWorklet extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    const n = channel.length;
    const pcm = new Int16Array(n);
    let sumSq = 0;
    for (let i = 0; i < n; i++) {
      let s = channel[i];
      if (s > 1) s = 1;
      else if (s < -1) s = -1;
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      sumSq += s * s;
    }
    const rms = Math.sqrt(sumSq / n);
    // Transfer de buffer (zero-copy) i.p.v. te kopiëren.
    this.port.postMessage({ pcm: pcm.buffer, rms }, [pcm.buffer]);
    return true;
  }
}

registerProcessor("stt-pcm-worklet", SttPcmWorklet);
