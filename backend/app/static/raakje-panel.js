// The Assistent panel (CR-11 K8, #1562; end state §3.15): one component for the
// back office (docked) and the public site (the bell). The markup is
// `_raakje_panel.html`, the geometry `.raakje-panel` in the stylesheet.
//
// - Opens on the window event `raakje-toggle` (the trigger in the top bar, the
//   bell); X or Escape closes and returns the focus to what opened it; a click
//   beside the panel does not close it.
// - Docked: the content moves aside (`assistant-open` on <html>), and the panel
//   stays open over a navigation. It asks the server for the context of the
//   screen it stands beside; when that context changes, the conversation starts
//   anew.
// - An answer that arrives for a conversation that is gone is not shown: another
//   context replaces the whole block, the form that asked with it, and htmx drops
//   the answer of an element that left the page (measured: no guard of our own
//   is needed — `tests_e2e/test_assistant_panel.py` holds it).
(function () {
  var DOCK = '(min-width: 1440px)';

  // The question field's height (#1617): ONE function, called from every path
  // that changes the value — typed or pasted (the field's `input` event, which
  // dictation fires too), set by a suggestion, kept after a question that was
  // not answered, emptied after an answer, and shown again when the panel
  // opens. The field is as high as its content, up to its CSS max-height
  // (`max-h-[120px]` on the control — the one place that number stands), after
  // which it scrolls inside itself. `scrollHeight` leaves the border out and
  // the height includes it, so the border is added: without it the last line
  // stood 2 px short and the field showed a scrollbar.
  window.raakjeFit = function (field) {
    if (!field) return;
    field.style.height = 'auto';
    // Not laid out (the panel is closed): nothing to measure, the next call fits.
    if (!field.scrollHeight) return;
    var edge = field.offsetHeight - field.clientHeight;
    var max = parseFloat(window.getComputedStyle(field).maxHeight) || Infinity;
    field.style.height = Math.min(field.scrollHeight + edge, max) + 'px';
  };

  window.raakjePanel = function (opts) {
    return {
      open: false,
      opener: null,

      init: function () {
        var self = this;
        if (!opts.contextUrl) return;
        // The screen changed (a navigation, a filter that landed in the address):
        // the trigger follows, and an open panel asks for its context again.
        var changed = function () { self.screenChanged(); };
        document.body.addEventListener('htmx:pushedIntoHistory', changed);
        document.body.addEventListener('htmx:replacedInHistory', changed);
        window.addEventListener('popstate', function () { setTimeout(changed, 0); });
        try {
          if (sessionStorage.getItem('raak-assistent') === '1' && window.matchMedia(DOCK).matches) this.show(null);
        } catch (e) { /* no storage: the panel simply starts closed */ }
      },

      // Below the docking width the panel is a dialog over a blocked background.
      modal: function () { return !(opts.docked && window.matchMedia(DOCK).matches); },

      toggle: function (event) {
        if (this.open) this.hide(); else this.show((event && event.detail && event.detail.opener) || document.activeElement);
      },

      show: function (opener) {
        var self = this;
        this.opener = opener;
        this.open = true;
        if (opts.docked) document.documentElement.classList.add('assistant-open');
        this.remember('1');
        if (opts.contextUrl) this.load();
        this.$nextTick(function () { self.focusField(); });
      },

      hide: function () {
        this.open = false;
        document.documentElement.classList.remove('assistant-open');
        this.remember('0');
        var back = this.opener && document.body.contains(this.opener) ? this.opener : document.querySelector('[data-raakje-trigger]');
        if (back) back.focus();
      },

      remember: function (value) {
        if (!opts.docked) return;
        try { sessionStorage.setItem('raak-assistent', value); } catch (e) { /* fine */ }
      },

      focusField: function () {
        var field = this.$refs.inner.querySelector('textarea') || this.$refs.inner.querySelector('[data-panel-close]');
        if (field) field.focus({ preventScroll: true });
        window.raakjeFit(this.$refs.inner.querySelector('textarea'));
      },

      // The context this panel shows now ("" before the first load).
      key: function () {
        var block = this.$refs.inner.querySelector('[data-context-key]');
        return block ? block.dataset.contextKey : '';
      },

      // Ask the context of the screen. The server answers 204 while it is the
      // one already shown, so a conversation survives a page of a list or a tab
      // of the same record; another context replaces the whole block.
      load: function () {
        var self = this;
        window.htmx.ajax('GET', opts.contextUrl + '?huidig=' + encodeURIComponent(this.key()), {
          target: this.$refs.inner, swap: 'innerHTML'
        }).then(function () { if (self.open) self.focusField(); });
      },

      screenChanged: function () {
        window.htmx.trigger(document.body, 'raakje-screen');
        if (this.open) this.load();
      },

      // A suggestion of the screen: asked as it stands.
      ask: function (question) {
        var form = this.$refs.inner.querySelector('[data-raakje-form]');
        if (!form) return;
        var field = form.querySelector('textarea');
        field.value = question;
        window.raakjeFit(field);
        form.requestSubmit();
      }
    };
  };

  // After an answer: the field empties and shrinks — unless the question was not
  // answered, then it stays ("Je vraag staat er nog") at the height it needs.
  window.raakjeAfterAnswer = function (form, event) {
    if (event.detail.elt !== form) return;
    var xhr = event.detail.xhr;
    var field = form.querySelector('textarea');
    if (!event.detail.successful || (xhr && xhr.getResponseHeader('X-Raakje-Failed') === '1')) {
      window.raakjeFit(field);
      return;
    }
    field.value = '';
    window.raakjeFit(field);
    var talk = form.parentElement.querySelector('[data-panel-conversation]');
    if (talk) talk.scrollTop = talk.scrollHeight;
  };

  // The bell above the action bar (#1589; end state §2.6). On a phone and a
  // tablet a form's action bar stands where the bell stands: while that bar is
  // in view the bell sits 16 px above it, and it returns to the bottom edge
  // when the bar is out of view. From 1 200 px the bar ends left of the bell.
  // The place is one custom property; the bell and its window read it.
  var bellTick = false;
  function placeBell() {
    bellTick = false;
    var bar = document.querySelector('.record-bar');
    var bottom = null;
    if (bar && window.innerWidth < 1200) {
      var box = bar.getBoundingClientRect();
      // In view where the bell stands: the bell's own place is the lowest
      // 88 px of the window (56 px and 16 px on either side). A bar that has
      // scrolled up past that leaves the bell where it belongs.
      if (box.height && box.top < window.innerHeight && box.bottom > window.innerHeight - 88) {
        bottom = Math.max(16, Math.round(window.innerHeight - box.top) + 16);
      }
    }
    var root = document.documentElement;
    if (bottom === null) root.style.removeProperty('--bell-bottom');
    else root.style.setProperty('--bell-bottom', bottom + 'px');
  }
  function askBell() {
    if (bellTick) return;
    bellTick = true;
    window.requestAnimationFrame(placeBell);
  }
  window.addEventListener('scroll', askBell, { passive: true });
  window.addEventListener('resize', askBell);
  document.addEventListener('DOMContentLoaded', askBell);
  document.addEventListener('htmx:afterSettle', askBell);

})();
