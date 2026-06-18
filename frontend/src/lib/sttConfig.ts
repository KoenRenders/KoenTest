// STT-config voor de frontend (#282/#290). De strategie STT_MODE wordt build-time
// ingebakken via NEXT_PUBLIC_STT_MODE (compose-build-arg ${STT_MODE}); default
// browser_only → de Voxtral-fallback is dan dark (niet actief).
export type SttMode = "browser_only" | "native_first" | "provider_only";

const RAW = (process.env.NEXT_PUBLIC_STT_MODE || "browser_only").toLowerCase();

export const STT_MODE: SttMode =
  RAW === "native_first" || RAW === "provider_only" ? RAW : "browser_only";

// Mag de provider (Voxtral) gebruikt worden voor browsers zonder (werkende) native STT?
export const STT_PROVIDER_ENABLED = STT_MODE === "native_first" || STT_MODE === "provider_only";

// Moet ALTIJD via de provider (ook als de browser native STT heeft)? — bv. EU/GDPR.
export const STT_PROVIDER_ONLY = STT_MODE === "provider_only";

// VAD/auto-stop-timers — UX-fijnafstemming (constante, #282). De échte kostrem zit
// server-side (STT_IDLE_TIMEOUT_SECONDS + audio-caps).
export const VAD_SILENCE_MS = 3000; // stop na 3 s stilte ná spraak
export const NO_SPEECH_MS = 8000; // mic open maar nooit gesproken → stop
export const STT_SAMPLE_RATE = 16000; // Voxtral: pcm_s16le @ 16 kHz mono
