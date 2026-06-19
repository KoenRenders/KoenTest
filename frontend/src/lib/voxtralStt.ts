// Voxtral-spraakinvoer-client (#282). Verbindt de mic met onze eigen WebSocket-proxy
// (/api/v1/stt/voxtral), die naar Voxtral Realtime (Mistral, EU) doorzet. Verantwoordelijk
// voor: toegangsgating (pas verbinden mét een live mic-track), audio → 16 kHz mono PCM16
// via een AudioWorklet, VAD-stilte-detectie + auto-stop (en bij tab-wissel), en netjes
// álle tracks sluiten bij stop. De API-key blijft serverside; de browser praat enkel met
// onze proxy.
import { NO_SPEECH_MS, STT_SAMPLE_RATE, VAD_SILENCE_MS } from "./sttConfig";

export type SttState = "connecting" | "listening" | "stopped";

export interface VoxtralSttCallbacks {
  /** Groeiende (tussentijdse) transcriptie tot nu toe. */
  onPartial?: (text: string) => void;
  /** Afgewerkte transcriptie. */
  onFinal?: (text: string) => void;
  /** Fout (code = DOMException-naam of 'ws'/'audio'); message is gebruikersvriendelijk. */
  onError?: (code: string, message: string) => void;
  onStateChange?: (state: SttState) => void;
}

// Drempel waaronder we een audioblok als 'stilte' beschouwen (RMS van [-1,1]-samples).
const SILENCE_RMS = 0.012;

function sttWsUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "";
  if (base.startsWith("http")) {
    return base.replace(/^http/, "ws") + "/api/v1/stt/voxtral";
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/v1/stt/voxtral`;
}

export class VoxtralStt {
  private ws: WebSocket | null = null;
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private noSpeechTimer: ReturnType<typeof setTimeout> | null = null;
  private transcript = "";
  private spokeOnce = false;
  private stopped = false;
  private readonly cb: VoxtralSttCallbacks;

  constructor(cb: VoxtralSttCallbacks) {
    this.cb = cb;
  }

  async start(): Promise<void> {
    this.cb.onStateChange?.("connecting");

    // 1) Toegangsgating: pas verder zodra getUserMedia een live track teruggeeft.
    // In een niet-beveiligde context (geen https) is mediaDevices undefined — vooral
    // Firefox is hier strikt. Dat expliciet benoemen i.p.v. een generieke fout.
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      this.cleanup();
      this.cb.onError?.(
        "insecure-context",
        "Spraakinvoer vereist een beveiligde verbinding (https).",
      );
      this.cb.onStateChange?.("stopped");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      const name = (e as DOMException)?.name || "Error";
      const message =
        name === "NotAllowedError"
          ? "Microfoon-toegang geweigerd."
          : name === "NotFoundError"
            ? "Geen microfoon gevonden."
            : name === "NotReadableError"
              ? "Microfoon is in gebruik door een andere app."
              : `Microfoon kon niet gestart worden (${name}).`;
      this.cleanup();
      this.cb.onError?.(name, message);
      this.cb.onStateChange?.("stopped");
      return;
    }
    this.stream = stream;
    if (this.stopped) {
      this.cleanup();
      return;
    }

    // 2) Audio-keten: AudioContext op 16 kHz (browser resamplet de mic) + worklet → PCM16.
    try {
      this.ctx = new AudioContext({ sampleRate: STT_SAMPLE_RATE });
      await this.ctx.audioWorklet.addModule("/stt-pcm-worklet.js");
      const source = this.ctx.createMediaStreamSource(stream);
      this.node = new AudioWorkletNode(this.ctx, "stt-pcm-worklet");
      this.node.port.onmessage = (ev: MessageEvent) =>
        this.onAudio(ev.data as { pcm: ArrayBuffer; rms: number });
      // Verbind via een gemute gain naar de uitgang: sommige browsers houden de
      // verwerkingsgraaf anders niet levend. We willen geen hoorbare echo → gain 0.
      const sink = this.ctx.createGain();
      sink.gain.value = 0;
      source.connect(this.node);
      this.node.connect(sink);
      sink.connect(this.ctx.destination);
    } catch {
      this.cleanup();
      this.cb.onError?.("audio", "Audio kon niet gestart worden.");
      this.cb.onStateChange?.("stopped");
      return;
    }

    // 3) WebSocket naar onze proxy.
    try {
      this.ws = new WebSocket(sttWsUrl());
      this.ws.binaryType = "arraybuffer";
      this.ws.onopen = () => {
        if (this.stopped) {
          this.stop();
          return;
        }
        this.cb.onStateChange?.("listening");
        this.armNoSpeech();
      };
      this.ws.onmessage = (ev: MessageEvent) => this.onWsMessage(ev);
      this.ws.onerror = () => this.cb.onError?.("ws", "Verbinding met de spraakdienst mislukt.");
      this.ws.onclose = () => this.finish();
    } catch {
      this.cleanup();
      this.cb.onError?.("ws", "Verbinding met de spraakdienst mislukt.");
      this.cb.onStateChange?.("stopped");
      return;
    }

    // 4) Auto-stop wanneer het tabblad naar de achtergrond gaat.
    document.addEventListener("visibilitychange", this.onVisibility);
  }

  private onVisibility = () => {
    if (document.hidden) this.stop();
  };

  private onAudio(data: { pcm: ArrayBuffer; rms: number }) {
    if (this.stopped || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(data.pcm);
    if (data.rms >= SILENCE_RMS) {
      // Er wordt gesproken: no-speech-cap opheffen en de stilte-timer herstarten.
      this.spokeOnce = true;
      this.clearNoSpeech();
      this.armSilence();
    }
  }

  private armSilence() {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    this.silenceTimer = setTimeout(() => {
      if (this.spokeOnce) this.stop(); // 3 s stilte ná spraak → afronden
    }, VAD_SILENCE_MS);
  }

  private armNoSpeech() {
    this.clearNoSpeech();
    this.noSpeechTimer = setTimeout(() => {
      if (!this.spokeOnce) this.stop(); // mic open maar nooit gesproken → stop
    }, NO_SPEECH_MS);
  }

  private clearNoSpeech() {
    if (this.noSpeechTimer) {
      clearTimeout(this.noSpeechTimer);
      this.noSpeechTimer = null;
    }
  }

  private onWsMessage(ev: MessageEvent) {
    if (typeof ev.data !== "string") return;
    let data: { type?: string; text?: string };
    try {
      data = JSON.parse(ev.data);
    } catch {
      return;
    }
    if (!data || !data.type) return;
    if (data.type === "partial") {
      this.transcript += data.text || "";
      this.cb.onPartial?.(this.transcript.trim());
    } else if (data.type === "final") {
      this.transcript = data.text || this.transcript;
      this.cb.onFinal?.(this.transcript.trim());
    }
  }

  /** Stop opnemen: signaleer einde-audio aan de server en sluit de keten. */
  stop() {
    if (this.stopped) return;
    this.stopped = true;
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "stop" }));
      }
    } catch {
      /* socket al weg — negeren */
    }
    // Mic + audio meteen vrijgeven; de WS laten we open om het eindtranscript te
    // ontvangen (server sluit na de 'stop' zelf → onclose → finish()).
    this.releaseMedia();
  }

  private finish() {
    this.cleanup();
    this.cb.onStateChange?.("stopped");
  }

  /** Geef mic + audiocontext vrij (dooft het tab-indicatorlampje), WS blijft. */
  private releaseMedia() {
    if (this.silenceTimer) {
      clearTimeout(this.silenceTimer);
      this.silenceTimer = null;
    }
    this.clearNoSpeech();
    document.removeEventListener("visibilitychange", this.onVisibility);
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    try {
      this.node?.disconnect();
    } catch {
      /* */
    }
    this.node = null;
    if (this.ctx && this.ctx.state !== "closed") {
      this.ctx.close().catch(() => {});
    }
    this.ctx = null;
  }

  private cleanup() {
    this.stopped = true;
    this.releaseMedia();
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        /* */
      }
      this.ws = null;
    }
  }
}
