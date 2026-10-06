// CR-17 spike — Trix comparison page, only for the load-time measurement.
(function () {
  "use strict";
  window.addEventListener("load", function () {
    document.body.dataset.editorReady = String(performance.now());
  });
})();
