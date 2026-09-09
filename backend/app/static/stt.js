// Spraakinvoer-eiland (#282, herbouwd na de React-exit — #405/#404-restpunt).
// Twee paden, gekozen via data-stt-mode op de knop:
//   - native (browser_only/native_first): Web Speech API van de browser;
//   - provider (native_first-fallback/provider_only): mic → AudioWorklet → PCM16
//     → onze eigen WebSocket-proxy /api/v1/stt/voxtral (de Voxtral-key blijft
//     serverside; de browser praat enkel met de proxy).
//
// #772: NIEMAND herbemonstert meer met de hand. Wij vragen de browser om 16 kHz en
// proberen de context daar ook op te zetten; lukt dat, dan heeft de browser het
// gedaan — mét zijn eigen anti-aliasfilter. Lukt het niet, dan draait alles op de
// snelheid van het apparaat en vertellen we Voxtral wélke snelheid dat is. Onze
// eigen resampler (#751) deed lineaire interpolatie zonder filter en vouwde alles
// boven 8 kHz terug als ruis; Voxtral herkende er geen spraak in.
// VAD/auto-stop: 3 s stilte ná spraak, 8 s zonder spraak, en bij tab-wissel.
(function () {
  "use strict";

  // De snelheid die Voxtral het liefst krijgt (pcm_s16le @ 16 kHz mono). Het is een
  // VOORKEUR, geen eis: krijgen we haar niet, dan gaat de echte snelheid mee naar de
  // server in plaats van dat wij gaan herbemonsteren.
  var DOEL_RATE = 16000;

  var VAD_SILENCE_MS = 3000;
  var NO_SPEECH_MS = 8000;
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
    // #772, weg A: vraag het aan de BRON. `ideal` en niet `exact` — gemeten in
    // Chromium levert `exact: 16000` een OverconstrainedError op een apparaat dat
    // alleen 48 kHz kan, en dan start de spraakinvoer helemaal niet meer.
    navigator.mediaDevices.getUserMedia({
      audio: { sampleRate: { ideal: DOEL_RATE }, channelCount: { ideal: 1 } }
    }).then(function (stream) {
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

  // #772: twee pogingen, in deze volgorde — en de tweede is niet zomaar een
  // terugval maar het bewezen pad uit #751.
  //
  //   1. context op 16 kHz. Slaagt `createMediaStreamSource`, dan lopen stroom en
  //      context gelijk en heeft de BROWSER het herbemonsteren gedaan.
  //   2. context zonder opties, dus op de snelheid van het apparaat. Firefox weigert
  //      te koppelen zodra de twee verschillen:
  //
  //        NotSupportedError — AudioContext.createMediaStreamSource: Connecting
  //        AudioNodes from AudioContexts with different sample-rate is currently not
  //        supported.
  //
  //      Op deze weg gaat de echte snelheid mee naar de server (zie `_connect`).
  //
  // Waarom PROBEREN en niet uitlezen: `getSettings().sampleRate` is precies wat je
  // hier zou willen, maar Firefox levert dat veld niet — gemeten met een nepapparaat
  // in playwright-firefox: `sampleRate` ontbreekt in de settings, terwijl Chromium
  // het gewoon meldt. In de browser waar deze storing thuishoort is uitlezen dus
  // geen optie, en dan is een poging de enige eerlijke meting.
  VoxtralStt.prototype._openAudio = function (stream) {
    var opties = [{ sampleRate: DOEL_RATE }, null];
    var stap = "de audiocontext aanmaken";
    var laatste = null;
    for (var i = 0; i < opties.length; i++) {
      var ctx = null;
      try {
        ctx = opties[i] ? new AudioContext(opties[i]) : new AudioContext();
      } catch (e) {
        laatste = e;
        continue;
      }
      try {
        return { ctx: ctx, source: ctx.createMediaStreamSource(stream) };
      } catch (e) {
        stap = "de microfoon koppelen";
        laatste = e;
        // Opruimen mag de melding niet kapen: een fout in `close()` zou anders de
        // reden vervangen waarom het koppelen niet lukte.
        try { ctx.close(); } catch (sluitFout) { /* genegeerd */ }
      }
    }
    this._audioFout(stap, laatste);
    return null;
  };

  VoxtralStt.prototype._startAudio = function (stream) {
    var self = this;
    var audio = self._openAudio(stream);
    if (!audio) return;
    self.ctx = audio.ctx;
    // #751: drie aparte stappen met drie aparte meldingen. Ze hingen alle drie aan
    // dezelfde `.catch()` van addModule, dus het laden van de worklet, het koppelen
    // van de stroom en het opzetten van de graaf gaven één identieke zin. Dat heeft
    // dit onderzoek vier vermoedens gekost: de code kende de reden en zei niet wélke
    // stap ze betrof.
    // #773: het adres van de worklet komt uit een data-attribuut op het script-tag,
    // want alleen de server kent de inhoudshash. Zonder die versie zou de browser wél
    // de nieuwe `stt.js` ophalen (die staat mét versie in de HTML) en dáárna de oude
    // worklet uit zijn cache halen — de helft van een fix, en dat is lastiger te
    // herkennen dan geen fix.
    var tag = document.querySelector("script[data-worklet]");
    self.ctx.audioWorklet.addModule(
      (tag && tag.dataset.worklet) || "/static/stt-pcm-worklet.js"
    ).then(function () {
      var sink;
      try {
        self.node = new AudioWorkletNode(self.ctx, "stt-pcm-worklet");
        self.node.port.onmessage = function (ev) { self._onAudio(ev.data); };
        // Gemute gain naar de uitgang: houdt de graaf levend zonder echo.
        sink = self.ctx.createGain();
        sink.gain.value = 0;
        audio.source.connect(self.node);
        self.node.connect(sink);
        sink.connect(self.ctx.destination);
      } catch (e) {
        self._audioFout("de audiograaf opzetten", e);
        return;
      }
      self._connect();
    }).catch(function (e) {
      self._audioFout("de worklet laden", e);
    });
  };

  // #751: de onderliggende fout NIET weggooien, en zeggen wélke stap faalde. Beide
  // catch-blokken gaven exact dezelfde zin ("Audio kon niet gestart worden."), en de
  // reden die de browser mét naam levert kwam nergens terecht — ook de console bleef
  // leeg. Dat kostte vier vermoedens vóór iemand de echte melding zag. Zelfde klasse
  // als #723: de code kent de reden en gooit ze weg.
  VoxtralStt.prototype._audioFout = function (stap, e) {
    var reden = e && (e.name || e.message) ? (e.name || "") + (e.message ? ": " + e.message : "") : "";
    if (window.console && console.error) {
      console.error("[stt] audio kon niet starten bij: " + stap, e);
    }
    this._fail("audio", "Audio kon niet gestart worden bij " + stap + "."
                        + (reden ? " (" + reden + ")" : ""));
  };

  VoxtralStt.prototype._connect = function () {
    var self = this;
    try {
      self.ws = new WebSocket(wsUrl());
      self.ws.binaryType = "arraybuffer";
      self.ws.onopen = function () {
        if (self.stopped) { self.stop(); return; }
        // #772: als éérste bericht, vóór één byte audio — de server moet de snelheid
        // kennen op het moment dat hij de sessie bij Voxtral opent. Dit is de
        // snelheid van de CONTEXT en niet die van het apparaat: de worklet levert
        // wat de context hem geeft, en dat is wat er over de lijn gaat.
        self.ws.send(JSON.stringify({
          type: "start", sample_rate: Math.round(self.ctx.sampleRate)
        }));
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

  // #570: een foutmelding hoort niet in de placeholder. Die staat in een smal veld
  // en wordt afgekapt — Koen las "Spraakinvoer vereist een bev…" en verder niets. En
  // ze verdwijnt zodra je begint te typen, precies wanneer je haar nodig hebt.
  // Zelfde vorm als de melding in het publieke formulier (#741).
  //
  // #751: ze hangt ONDER het formulier en niet erin. Het formulier is een
  // `flex gap-2 items-end` zonder `flex-wrap`, dus als vierde kind werd de melding
  // naast het veld en de twee knoppen geperst en afgeknipt — precies de reden die we
  // nodig hadden was daardoor onleesbaar. De vorm is niet aan te passen zonder de
  // knoppenrij te verbouwen; ernaast zetten is de kleinere en duidelijkere ingreep.
  function toonMelding(btn, tekst) {
    var vorm = btn.closest("form") || btn.parentNode;
    var doel = vorm.parentNode || vorm;
    var vorige = doel.querySelector("[data-stt-melding]");
    if (vorige) { vorige.remove(); }
    if (!tekst) { return; }
    var p = document.createElement("p");
    p.setAttribute("data-stt-melding", "");
    p.setAttribute("role", "alert");
    p.className = "text-xs text-red-800 mt-1 px-2";
    p.textContent = tekst;
    if (vorm.nextSibling) { doel.insertBefore(p, vorm.nextSibling); }
    else { doel.appendChild(p); }
  }

  // ── Knop-wiring: <button data-stt-target="#input" data-stt-mode="..."> ────
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-stt-target]").forEach(function (btn) {
      var input = document.querySelector(btn.getAttribute("data-stt-target"));
      var mode = btn.getAttribute("data-stt-mode") || "browser_only";
      if (!input) return;
      if (mode === "browser_only" && !nativeAvailable()) { btn.hidden = true; return; }
      var actief = null;
      // #570: de knop draagt haar drie standen als SVG mee (kit-iconen, niet 🎙/⏹/…).
      // Losse tekens renderen per lettertype en OS anders, en deze widget staat op
      // élke publieke pagina.
      //
      // #762: bij elke wissel uitlezen in plaats van één keer bij het laden. Een
      // attribuut is de bron; het cachen ervan voegt een tweede toestand toe die
      // alleen maar kan verlopen. De terugval op de huidige inhoud houdt knoppen
      // zonder deze attributen werkend.
      var start = btn.innerHTML;
      function icoon(stand) {
        return btn.getAttribute("data-icon-" + stand) || start || "";
      }

      function cb() {
        return {
          onPartial: function (t) { input.value = t; },
          onFinal: function (t) { input.value = t; input.focus(); },
          onError: function (code, message) { toonMelding(btn, message); },
          onStateChange: function (state) {
            btn.innerHTML = state === "listening" ? icoon("listening")
                          : state === "connecting" ? icoon("connecting") : icoon("idle");
            if (state === "stopped") actief = null;
          },
        };
      }

      btn.addEventListener("click", function () {
        toonMelding(btn, "");
        if (actief) { actief.stop(); return; }
        var useNative = mode !== "provider_only" && nativeAvailable();
        if (useNative) {
          actief = startNative(cb());
        } else if (mode === "browser_only") {
          toonMelding(btn, "Spraakherkenning niet beschikbaar in deze browser.");
        } else {
          actief = new VoxtralStt(cb());
          actief.start();
        }
      });
    });
  });
})();
