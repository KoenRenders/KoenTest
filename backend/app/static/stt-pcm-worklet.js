// AudioWorklet voor de Voxtral-spraakinvoer (#282). Draait in de audio-thread: neemt
// de mic-blokken (Float32 op de snelheid van de AudioContext), herbemonstert ze naar
// 16 kHz, zet ze om naar 16-bit PCM (pcm_s16le, wat Voxtral verwacht) en stuurt elk
// blok naar de hoofdthread, samen met de RMS-energie voor stilte-detectie (VAD).
//
// #751: het herbemonsteren gebeurt HIER en niet meer door de AudioContext op 16 kHz
// te zetten. Firefox weigert `createMediaStreamSource` wanneer de stroom en de
// context een andere snelheid hebben — met zoveel woorden:
//
//   NotSupportedError — AudioContext.createMediaStreamSource: Connecting AudioNodes
//   from AudioContexts with different sample-rate is currently not supported.
//
// Een microfoon op Linux levert vrijwel altijd 48 kHz (PipeWire), dus die combinatie
// kwam er altijd. Chrome herbemonstert stilzwijgend; daar viel het nooit op.
//
// De RMS wordt op de HERBEMONSTERDE stroom berekend: de stiltedetectie hoort te
// gelden voor wat er verstuurd wordt, niet voor wat er binnenkwam.
const DOEL_RATE = 16000;

class SttPcmWorklet extends AudioWorkletProcessor {
  constructor() {
    super();
    // Positie van het volgende uitgangssample, uitgedrukt in ingangssamples en
    // relatief aan het begin van het huidige blok. Blijft tussen blokken staan,
    // anders ontstaat er bij elke blokgrens een sprongetje.
    this.pos = 0;
    this.vorige = null; // laatste sample van het vorige blok, voor de interpolatie
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const channel = input[0];
    if (!channel || channel.length === 0) return true;

    const stap = sampleRate / DOEL_RATE; // 3 bij 48 kHz, 1 bij 16 kHz
    const n = channel.length;
    // Bij gelijke snelheid is `stap` precies 1 en loopt de lus sample voor sample —
    // dan is dit een doorgeefluik. Dat geval mag niet stuk: een apparaat dat 16 kHz
    // wél levert moet blijven werken.
    const uit = [];
    let p = this.pos;
    while (p < n) {
      const i = Math.floor(p);
      const f = p - i;
      // i is -1 wanneer de vorige blokgrens middenin een interval viel; dan komt het
      // linkersample uit het vorige blok.
      const s0 = i < 0 ? (this.vorige === null ? channel[0] : this.vorige) : channel[i];
      const s1 = i + 1 < n ? channel[i + 1] : channel[n - 1];
      uit.push(s0 + (s1 - s0) * f);
      p += stap;
    }
    this.pos = p - n;
    this.vorige = channel[n - 1];

    const m = uit.length;
    if (m === 0) return true;
    const pcm = new Int16Array(m);
    let sumSq = 0;
    for (let i = 0; i < m; i++) {
      let s = uit[i];
      if (s > 1) s = 1;
      else if (s < -1) s = -1;
      pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      sumSq += s * s;
    }
    const rms = Math.sqrt(sumSq / m);
    // Transfer de buffer (zero-copy) i.p.v. te kopiëren.
    this.port.postMessage({ pcm: pcm.buffer, rms }, [pcm.buffer]);
    return true;
  }
}

registerProcessor("stt-pcm-worklet", SttPcmWorklet);
