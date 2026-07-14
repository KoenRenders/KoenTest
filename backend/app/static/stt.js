// Spraakinvoer-eiland (#282, herbouwd na de React-exit — #405/#404-restpunt).
// Twee paden, gekozen via data-stt-mode op de knop:
//   - native (browser_only/native_first): Web Speech API van de browser;
//   - provider (native_first-fallback/provider_only): mic → 16 kHz PCM16 via
//     een AudioWorklet → onze eigen WebSocket-proxy /api/v1/stt/voxtral
//     (de Voxtral-key blijft serverside; de browser praat enkel met de proxy).
// VAD/auto-stop: 3 s stilte ná spraak, 8 s zonder spraak, en bij tab-wissel.
(function () {
  "use strict";

  var VAD_SILENCE_MS = 3000;
  var NO_SPEECH_MS = 8000;
  var STT_SAMPLE_RATE = 16000;
  var SILENCE_RMS = 0.012;

  function wsUrl() {
    var proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return proto + "//" + window.location.host + "/api/v1/stt/voxtral";
  }

  // ── Provider-pad (Voxtral via onze proxy) ────────────────────────────────
  function VoxtralStt(cb) {
    this.cb = cb;
    this.ws = null;
    this.ctx = null;
    this.stream = null;
    this.node = null;
    this.silenceTimer = null;
    this.noSpeechTimer = null;
    this.transcript = "";
    this.spokeOnce = false;
    this.stopped = false;
    this._onVisibility = this._visibility.bind(this);
  }

  VoxtralStt.prototype.start = function () {
    var self = this;
    self.cb.onStateChange("connecting");
    if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      self._fail("insecure-context", "Spraakinvoer vereist een beveiligde verbinding (https).");
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      self.stream = stream;
      if (self.stopped) { self._cleanup(); return; }
      self._startAudio(stream);
    }).catch(function (e) {
      var name = (e && e.name) || "Error";
      var message = name === "NotAllowedError" ? "Microfoon-toegang geweigerd."
        : name === "NotFoundError" ? "Geen microfoon gevonden."
        : name === "NotReadableError" ? "Microfoon is in gebruik door een andere app."
        : "Microfoon kon niet gestart worden (" + name + ").";
      self._fail(name, message);
    });
  };

  VoxtralStt.prototype._startAudio = function (stream) {
    var self = this;
    try {
      self.ctx = new AudioContext({ sampleRate: STT_SAMPLE_RATE });
      self.ctx.audioWorklet.addModule("/static/stt-pcm-worklet.js").then(function () {
        var source = self.ctx.createMediaStreamSource(stream);
        self.node = new AudioWorkletNode(self.ctx, "stt-pcm-worklet");
        self.node.port.onmessage = function (ev) { self._onAudio(ev.data); };
        // Gemute gain naar de uitgang: houdt de graaf levend zonder echo.
        var sink = self.ctx.createGain();
        sink.gain.value = 0;
        source.connect(self.node);
        self.node.connect(sink);
        sink.connect(self.ctx.destination);
        self._connect();
      }).catch(function () {
        self._fail("audio", "Audio kon niet gestart worden.");
      });
    } catch (e) {
      self._fail("audio", "Audio kon niet gestart worden.");
    }
  };

  VoxtralStt.prototype._connect = function () {
    var self = this;
    try {
      self.ws = new WebSocket(wsUrl());
      self.ws.binaryType = "arraybuffer";
      self.ws.onopen = function () {
        if (self.stopped) { self.stop(); return; }
        self.cb.onStateChange("listening");
        self._armNoSpeech();
      };
      self.ws.onmessage = function (ev) { self._onWsMessage(ev); };
      self.ws.onerror = function () { self.cb.onError("ws", "Verbinding met de spraakdienst mislukt."); };
      self.ws.onclose = function () { self._cleanup(); self.cb.onStateChange("stopped"); };
      document.addEventListener("visibilitychange", self._onVisibility);
    } catch (e) {
      self._fail("ws", "Verbinding met de spraakdienst mislukt.");
    }
  };

  VoxtralStt.prototype._visibility = function () { if (document.hidden) this.stop(); };

  VoxtralStt.prototype._onAudio = function (data) {
    if (this.stopped || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(data.pcm);
    if (data.rms >= SILENCE_RMS) {
      this.spokeOnce = true;
      this._clearNoSpeech();
      this._armSilence();
    }
  };

  VoxtralStt.prototype._armSilence = function () {
    var self = this;
    if (self.silenceTimer) clearTimeout(self.silenceTimer);
    self.silenceTimer = setTimeout(function () { if (self.spokeOnce) self.stop(); }, VAD_SILENCE_MS);
  };

  VoxtralStt.prototype._armNoSpeech = function () {
    var self = this;
    self._clearNoSpeech();
    self.noSpeechTimer = setTimeout(function () { if (!self.spokeOnce) self.stop(); }, NO_SPEECH_MS);
  };

  VoxtralStt.prototype._clearNoSpeech = function () {
    if (this.noSpeechTimer) { clearTimeout(this.noSpeechTimer); this.noSpeechTimer = null; }
  };

  VoxtralStt.prototype._onWsMessage = function (ev) {
    if (typeof ev.data !== "string") return;
    var data;
    try { data = JSON.parse(ev.data); } catch (e) { return; }
    if (!data || !data.type) return;
    if (data.type === "partial") {
      this.transcript += data.text || "";
      this.cb.onPartial(this.transcript.trim());
    } else if (data.type === "final") {
      this.transcript = data.text || this.transcript;
      this.cb.onFinal(this.transcript.trim());
    }
  };

  VoxtralStt.prototype.stop = function () {
    if (this.stopped) return;
    this.stopped = true;
    try {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify({ type: "stop" }));
      }
    } catch (e) { /* socket al weg */ }
    // Mic meteen vrij; de WS blijft open voor het eindtranscript (server sluit).
    this._releaseMedia();
  };

  VoxtralStt.prototype._releaseMedia = function () {
    if (this.silenceTimer) { clearTimeout(this.silenceTimer); this.silenceTimer = null; }
    this._clearNoSpeech();
    document.removeEventListener("visibilitychange", this._onVisibility);
    if (this.stream) { this.stream.getTracks().forEach(function (t) { t.stop(); }); this.stream = null; }
    try { if (this.node) this.node.disconnect(); } catch (e) { /* */ }
    this.node = null;
    if (this.ctx && this.ctx.state !== "closed") { this.ctx.close().catch(function () {}); }
    this.ctx = null;
  };

  VoxtralStt.prototype._cleanup = function () {
    this.stopped = true;
    this._releaseMedia();
    if (this.ws) { try { this.ws.close(); } catch (e) { /* */ } this.ws = null; }
  };

  VoxtralStt.prototype._fail = function (code, message) {
    this._cleanup();
    this.cb.onError(code, message);
    this.cb.onStateChange("stopped");
  };

  // ── Native-pad (Web Speech API) ──────────────────────────────────────────
  function nativeAvailable() {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  function startNative(cb) {
    var Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    var rec = new Rec();
    rec.lang = document.documentElement.lang || "nl-BE";
    rec.interimResults = true;
    rec.onresult = function (ev) {
      var text = "";
      for (var i = 0; i < ev.results.length; i++) text += ev.results[i][0].transcript;
      if (ev.results[ev.results.length - 1].isFinal) cb.onFinal(text.trim());
      else cb.onPartial(text.trim());
    };
    rec.onerror = function (ev) { cb.onError(ev.error || "native", "Spraakherkenning mislukt."); };
    rec.onend = function () { cb.onStateChange("stopped"); };
    cb.onStateChange("listening");
    rec.start();
    return { stop: function () { try { rec.stop(); } catch (e) { /* */ } } };
  }

  // ── Knop-wiring: <button data-stt-target="#input" data-stt-mode="..."> ────
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-stt-target]").forEach(function (btn) {
      var input = document.querySelector(btn.getAttribute("data-stt-target"));
      var mode = btn.getAttribute("data-stt-mode") || "browser_only";
      if (!input) return;
      if (mode === "browser_only" && !nativeAvailable()) { btn.hidden = true; return; }
      var actief = null;
      var origineel = btn.textContent;

      function cb() {
        return {
          onPartial: function (t) { input.value = t; },
          onFinal: function (t) { input.value = t; input.focus(); },
          onError: function (code, message) { input.placeholder = message; },
          onStateChange: function (state) {
            btn.textContent = state === "listening" ? "⏹" : state === "connecting" ? "…" : origineel;
            if (state === "stopped") actief = null;
          },
        };
      }

      btn.addEventListener("click", function () {
        if (actief) { actief.stop(); return; }
        var useNative = mode !== "provider_only" && nativeAvailable();
        if (useNative) {
          actief = startNative(cb());
        } else if (mode === "browser_only") {
          input.placeholder = "Spraakherkenning niet beschikbaar in deze browser.";
        } else {
          actief = new VoxtralStt(cb());
          actief.start();
        }
      });
    });
  });
})();
