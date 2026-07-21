// Voorlezen van Raakje-antwoorden (TTS, #568 — herbouwd na de React-exit, #405).
// Pariteit met de oude React-widget (#205/#241): een 🔊/🔇-toggle "voorlezen"
// en per antwoord een 🔈-knop. Volledig browser-side via de Web Speech API
// (speechSynthesis) — geen data verlaat de browser (EU-conform). De voorgelezen
// tekst is de innerText van het antwoord; markdown is server-side (#566) al naar
// HTML gerenderd, dus er zijn geen ruwe sterretjes meer om te strippen.
(function () {
  "use strict";

  // Geen TTS-ondersteuning → stil degraderen: verberg de toggles en stop.
  if (!("speechSynthesis" in window)) {
    document.addEventListener("DOMContentLoaded", function () {
      document.querySelectorAll("[data-tts-toggle]").forEach(function (b) {
        b.hidden = true;
      });
    });
    return;
  }

  var LS_KEY = "raakje-tts";
  function readAloud() { return localStorage.getItem(LS_KEY) === "1"; }
  function setReadAloud(on) {
    localStorage.setItem(LS_KEY, on ? "1" : "0");
    if (!on) window.speechSynthesis.cancel();
  }

  function pickVoice() {
    var vs = window.speechSynthesis.getVoices() || [];
    return vs.filter(function (v) {
      return (v.lang || "").toLowerCase().indexOf("nl") === 0;
    })[0] || null;
  }

  function speak(text) {
    var plain = (text || "").trim();
    if (!plain) return;
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(plain);
    u.lang = "nl-BE";
    var v = pickVoice();
    if (v) u.voice = v;
    window.speechSynthesis.speak(u);
  }

  function wireToggle(btn) {
    function paint() {
      btn.textContent = readAloud() ? "🔊" : "🔇";
      btn.setAttribute("aria-pressed", readAloud() ? "true" : "false");
    }
    paint();
    btn.addEventListener("click", function () {
      setReadAloud(!readAloud());
      paint();
    });
  }

  // Voeg aan een net binnengekomen antwoord een 🔈-knop toe en lees automatisch
  // voor als de toggle aanstaat. Eén keer per antwoord (guard via dataset).
  function decorateAnswer(el) {
    if (!el || el.dataset.ttsDone) return;
    el.dataset.ttsDone = "1";
    var text = el.innerText;
    var b = document.createElement("button");
    b.type = "button";
    b.textContent = "🔈";
    b.className = "ml-1 align-middle text-gray-400 hover:text-blue-700";
    b.title = "Lees voor";
    b.setAttribute("aria-label", "Lees dit antwoord voor");
    b.addEventListener("click", function () { speak(text); });
    el.appendChild(b);
    if (readAloud()) speak(text);
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-tts-toggle]").forEach(wireToggle);
  });

  // Nieuwe antwoorden komen via htmx binnen (beforeend-swap in het gesprek-paneel).
  document.body.addEventListener("htmx:afterSwap", function (e) {
    var scope = e.target || document;
    if (!scope.querySelectorAll) return;
    scope.querySelectorAll("[data-raakje-answer]").forEach(decorateAnswer);
  });
})();
