/* The record form of the kit (CR-11 block 9, #1561; design-system-end-state §3.6, §3.18).
 *
 * A record is edited as a whole and saved with ONE "Opslaan". This file gives
 * that form its states; the markup comes from `ui.action_bar(record=True)`,
 * `ui.save_refusal` and `ui.field`, and this file reads only data attributes:
 *
 *   [data-record-form]        the form; `data-message` is the selector of its
 *                             message line (where a refusal or a failure stands)
 *   [data-action-bar]         the bar: [data-form-save], [data-form-cancel],
 *                             [data-form-delete]; a <template data-save-failed>
 *   [data-save-refusal]       the banner; its [data-error-for] links name a
 *                             field (`slug`, `c.12.max_participants`) or a row (`c.12`)
 *   [data-field]              a field of `ui.field`, by the form's name
 *   [data-dirty-ignore]       controls that are no part of the record (a search)
 *
 * States:
 *   - changed or not: the form compared with what it was when it opened;
 *   - Annuleren with changes asks "Wijzigingen weggooien?"; leaving by a link
 *     asks "Deze pagina verlaten?"; closing the tab gets the browser's prompt.
 *     The safe choice is the filled, focused button. Never "save and leave";
 *   - saving: "Opslaan…", the form inert but looking the same;
 *   - refused: every refused field marked with its reason, a removed row that
 *     may not go put back, the focus on the first one, every value kept;
 *   - failed: "Opslaan is niet gelukt." with the reason, in the form — no toast;
 *   - Ctrl/⌘+S saves; Esc never closes the form.
 */
(function () {
  "use strict";
  if (window.raakRecordForm) return;

  /* The words of the two questions stand on the bar (`ui.action_bar`), where
     they are translated; the script only asks them. */
  function words(kind) {
    var bar = theBar();
    var data = bar ? bar.dataset : {};
    return kind === "discard"
      ? [data.discardTitle, data.discardText, data.discardOk, data.discardStay]
      : [data.leaveTitle, data.leaveText, data.leaveOk, data.leaveStay];
  }

  function theForm() {
    return document.querySelector("form[data-record-form]");
  }

  function theBar() {
    return document.querySelector("[data-action-bar]");
  }

  /* What the form holds, as text: every named control that belongs to it, in
     document order — so a moved, added or removed row is a change too. */
  function snapshot(form) {
    var parts = [];
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name || el.disabled || el.tagName === "BUTTON") return;
      if (el.closest("[data-dirty-ignore]")) return;
      if ((el.type === "checkbox" || el.type === "radio") && !el.checked) return;
      if (el.type === "file") {
        parts.push(el.name + "=" + Array.prototype.map.call(el.files, function (f) { return f.name + ":" + f.size; }).join(","));
        return;
      }
      parts.push(el.name + "=" + el.value);
    });
    return parts.join("\n");
  }

  function begin(form) {
    if (!form || form.raakInitial !== undefined) return;
    form.raakInitial = snapshot(form);
  }

  function isDirty(form) {
    return !!form && form.raakInitial !== undefined && !form.raakLeaving && snapshot(form) !== form.raakInitial;
  }

  function ask(onAccept, kind) {
    var w = words(kind);
    window.Alpine.store("confirm").ask(onAccept, w[1], w[2], { title: w[0], tone: "keep", cancelLabel: w[3] });
  }

  function dialogOpen() {
    return !!(window.Alpine && window.Alpine.store("confirm") && window.Alpine.store("confirm").open);
  }

  /* ── Annuleren and leaving ─────────────────────────────────────────────── */

  document.addEventListener(
    "click",
    function (event) {
      var form = theForm();
      if (!form || form.raakSaving) return;
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
      var link = event.target.closest("a[href]");
      if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
      var href = link.getAttribute("href");
      if (!href || href.charAt(0) === "#") return;
      if (link.closest("[data-dialog]") || !isDirty(form)) return;
      event.preventDefault();
      event.stopPropagation();
      var go = function () {
        leaveBy(form, link);
        link.click();
      };
      ask(go, link.hasAttribute("data-form-cancel") ? "discard" : "leave");
    },
    true
  );

  /* The guard steps aside for ONE action the user chose with "Weggooien"
     (#1660): `by` is the element that action starts from. When that action is
     over and the page is still here, the guard guards again — it used to stay
     off for the rest of the page, so a command that failed, or one that did
     not leave, left every later link unasked. */
  function leaveBy(form, by) {
    form.raakLeaving = true;
    form.raakLeavingBy = by;
  }

  /* Is this request a command outside the form — one that would redraw the
     record and lose the changes? */
  function commandOutside(form, source, verb) {
    if (!form || !source) return false;
    if (source === form || form.contains(source) || source.closest("[data-action-bar]")) return false;
    // The Assistent's panel stands BESIDE the record (#1659): a request in it
    // asks for a proposal and its answer lands in the panel — nothing redraws
    // the record, so it is no way out, whatever the form holds.
    if (source.closest("[data-raakje-panel]")) return false;
    return (verb || "get").toLowerCase() !== "get";
  }

  /* A command outside the form (a state command in Acties): the same question
     first. Asked at `htmx:confirm`, where htmx hands over the request itself:
     "Weggooien" resumes THAT request — a click as a click, a form's submit as
     a submit (#1660; repeating a click on the source did nothing for a
     form) — and the command's own question (`data-confirm`)
     comes after this one, once: until #1660 it was asked, then this one, then
     it again. In the capture phase, so this one is asked before the kit's
     confirm host hears the event. */
  document.addEventListener(
    "htmx:confirm",
    function (event) {
      var form = theForm();
      var source = event.detail.elt;
      if (!commandOutside(form, source, event.detail.verb)) return;
      if (form.raakPassing === source) {
        form.raakPassing = null; // the request this guard let through: asked already
        return;
      }
      if (form.raakSaving || !isDirty(form)) return;
      event.preventDefault();
      event.stopPropagation();
      var paused = event.detail;
      ask(function () {
        // htmx asks `htmx:confirm` once per request, and this guard took that
        // one: hand the paused request on to whoever else has a question (the
        // kit's confirm host, for a `data-confirm`). Nobody: it goes.
        form.raakPassing = source;
        var next = new CustomEvent("htmx:confirm", { bubbles: true, cancelable: true, detail: paused });
        if (source.dispatchEvent(next)) paused.issueRequest(true);
      }, "leave");
    },
    true
  );

  document.addEventListener("htmx:beforeRequest", function (event) {
    var form = theForm();
    var source = event.detail.elt;
    if (!commandOutside(form, source, event.detail.requestConfig.verb)) return;
    if (form.raakSaving) {
      event.preventDefault(); // never a command while a save is running
      return;
    }
    // The command goes: what it answers may send the browser on, and leaving
    // then asks nothing — for this one request.
    if (isDirty(form)) leaveBy(form, source);
  });

  /* The action the guard stepped aside for is over. An answer that sends the
     browser on keeps the guard aside until the page is gone. */
  document.addEventListener("htmx:afterRequest", function (event) {
    var form = theForm();
    if (!form || !form.raakLeavingBy || event.detail.elt !== form.raakLeavingBy) return;
    var xhr = event.detail.xhr;
    var goesOn = !!xhr && event.detail.successful &&
      !!(xhr.getResponseHeader("HX-Redirect") || xhr.getResponseHeader("HX-Location") || xhr.getResponseHeader("HX-Refresh"));
    if (goesOn) return;
    form.raakLeaving = false;
    form.raakLeavingBy = null;
  });

  window.addEventListener("beforeunload", function (event) {
    var form = theForm();
    if (!form || form.raakSaving || !isDirty(form)) return;
    event.preventDefault();
    event.returnValue = "";
  });

  /* ── Saving ────────────────────────────────────────────────────────────── */

  function setSaving(form, on) {
    form.raakSaving = on;
    form.inert = on;
    if (on) form.setAttribute("aria-busy", "true");
    else form.removeAttribute("aria-busy");
    var bar = theBar();
    if (!bar) return;
    if (on) bar.setAttribute("data-saving", "");
    else bar.removeAttribute("data-saving");
    var save = bar.querySelector("[data-form-save]");
    if (save) {
      save.disabled = on;
      save.querySelector("[data-save-idle]").hidden = on;
      save.querySelector("[data-save-busy]").hidden = !on;
    }
    Array.prototype.forEach.call(bar.querySelectorAll("[data-form-cancel], [data-form-delete]"), function (el) {
      el.inert = on;
    });
  }

  function messageLine(form) {
    return document.querySelector(form.getAttribute("data-message"));
  }

  function clearMarks(form) {
    var flow = form.closest("[data-form-flow]") || form;
    Array.prototype.forEach.call(flow.querySelectorAll("[data-refused-message]"), function (el) { el.remove(); });
    Array.prototype.forEach.call(flow.querySelectorAll("[data-refused]"), function (el) {
      el.removeAttribute("data-refused");
    });
    Array.prototype.forEach.call(flow.querySelectorAll("[data-refused-control]"), function (el) {
      el.removeAttribute("data-refused-control");
      el.removeAttribute("aria-invalid");
    });
  }

  document.addEventListener("htmx:beforeRequest", function (event) {
    var form = theForm();
    if (!form || event.detail.elt !== form || event.defaultPrevented) return;
    clearMarks(form);
    var line = messageLine(form);
    if (line) line.replaceChildren();
    setSaving(form, true);
  });

  /* A good answer that sends the browser on (`HX-Redirect` — the payment page,
     the saved registration): the form is done, so leaving it asks nothing. */
  document.addEventListener("htmx:beforeOnLoad", function (event) {
    var form = event.detail.elt;
    var xhr = event.detail.xhr;
    if (!form || !form.matches || !form.matches("form[data-record-form]") || !xhr) return;
    if (xhr.status < 300 && (xhr.getResponseHeader("HX-Redirect") || xhr.getResponseHeader("HX-Location"))) {
      form.raakLeaving = true;
    }
  });

  document.addEventListener("htmx:afterRequest", function (event) {
    var form = event.detail.elt;
    if (form && form.matches && form.matches("form[data-record-form]") && form.isConnected) setSaving(form, false);
  });

  /* ── Refused: the fields and rows the banner names ─────────────────────── */

  function controlOf(field) {
    return field.querySelector("input:not([type=hidden]), select, textarea");
  }

  function reasonNode(text) {
    var p = document.createElement("p");
    p.setAttribute("data-refused-message", "");
    p.textContent = text;
    return p;
  }

  function findRow(flow, place) {
    var groups = window.raakRepeatingGroup;
    if (!groups) return null;
    var rows = flow.querySelectorAll("[data-group-row]");
    for (var i = 0; i < rows.length; i += 1) {
      if (groups.placeOf(rows[i]) === place) return rows[i];
    }
    return groups.restore(place);
  }

  /* Mark one place; returns what to focus for it. */
  function mark(flow, place, text) {
    var field = flow.querySelector('[data-field="' + window.CSS.escape(place) + '"]');
    if (field) {
      var closed = field.closest("details:not([open])");
      if (closed) closed.open = true;
      field.setAttribute("data-refused", "");
      field.appendChild(reasonNode(text));
      var control = controlOf(field);
      if (control) {
        control.setAttribute("aria-invalid", "true");
        control.setAttribute("data-refused-control", "");
      }
      return control || field;
    }
    var row = place.split(".").length === 2 ? findRow(flow, place) : null;
    if (row) {
      row.setAttribute("data-refused", "");
      var body = row.querySelector("[data-row-body]") || row;
      body.insertBefore(reasonNode(text), body.firstChild);
      return row.querySelector("[data-row-menu-trigger]") || row;
    }
    return null;
  }

  function focusOn(target) {
    if (!target) return;
    if (!target.matches("input, select, textarea, button, a")) target.setAttribute("tabindex", "-1");
    target.focus({ preventScroll: true });
    target.scrollIntoView({ block: "center" });
  }

  function showRefusal(form, banner) {
    var flow = form.closest("[data-form-flow]") || form;
    var first = null;
    Array.prototype.forEach.call(banner.querySelectorAll("[data-error-for]"), function (link) {
      var target = mark(flow, link.getAttribute("data-error-for"), link.textContent);
      link.raakTarget = target;
      if (target && !first) first = target;
    });
    focusOn(first || banner);
  }

  document.addEventListener("htmx:afterSettle", function (event) {
    var form = theForm();
    if (!form) return;
    var line = messageLine(form);
    var banner = line && line.querySelector("[data-save-refusal]");
    if (banner && !banner.raakShown && event.target === line) {
      banner.raakShown = true;
      showRefusal(form, banner);
    }
  });

  /* A good answer that IS the result — the confirmation, the thank-you page —
     takes the form's place: its title gets the focus, so a screen reader hears
     what happened and the keyboard starts at the top of it. */
  document.addEventListener("htmx:afterSettle", function (event) {
    var page = event.target && event.target.querySelector && event.target.querySelector("[data-public-form-page][data-result] h1");
    if (page) page.focus({ preventScroll: true });
  });

  document.addEventListener("click", function (event) {
    var link = event.target.closest("[data-error-for]");
    if (!link) return;
    event.preventDefault();
    focusOn(link.raakTarget);
  });

  /* ── Failed: no answer, or an answer that is no refusal ────────────────── */

  document.addEventListener("record:save-failed", function (event) {
    var form = event.target;
    var bar = theBar();
    var line = messageLine(form);
    var template = bar && bar.querySelector("template[data-save-failed]");
    if (!line || !template) return;
    var banner = template.content.firstElementChild.cloneNode(true);
    banner.querySelector("[data-reason]").textContent = event.detail.reason;
    line.replaceChildren(banner);
    focusOn(banner);
  }, true);

  /* ── The keyboard ──────────────────────────────────────────────────────── */

  document.addEventListener("keydown", function (event) {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.key.toLowerCase() !== "s") return;
    var form = theForm();
    if (!form) return;
    event.preventDefault(); // never the browser's "save page" while editing a record
    if (form.raakSaving || dialogOpen()) return;
    var save = theBar() && theBar().querySelector("[data-form-save]");
    form.requestSubmit(save && save.form === form ? save : undefined);
  });

  /* ── The bar sticks, and says so (#1607) ─────────────────────────────────
     While the form is longer than the window the bar stands against the
     window's bottom and casts its shadow upward; at the form's end it is in
     the flow and casts none. Sticky has no state a stylesheet can read, so
     the bar gets `data-stuck` while its bottom is the window's bottom. */
  var stuckTick = false;
  function markStuck() {
    stuckTick = false;
    var bar = theBar();
    if (!bar) return;
    var box = bar.getBoundingClientRect();
    var edge = document.documentElement.clientHeight;
    var stuck = box.height > 0 && getComputedStyle(bar).position === "sticky" && Math.abs(box.bottom - edge) < 1;
    if (stuck !== bar.hasAttribute("data-stuck")) bar.toggleAttribute("data-stuck", stuck);
  }
  function askStuck() {
    if (stuckTick) return;
    stuckTick = true;
    window.requestAnimationFrame(markStuck);
  }
  window.addEventListener("scroll", askStuck, { passive: true });
  window.addEventListener("resize", askStuck);
  // The page growing or shrinking without a scroll — a row added, a section
  // unfolded — moves the form's end past the window's bottom or back.
  if (window.ResizeObserver) new ResizeObserver(askStuck).observe(document.documentElement);

  function init() {
    // After Alpine and the group script settled the form's first state.
    window.requestAnimationFrame(function () { begin(theForm()); markStuck(); });
  }
  document.addEventListener("DOMContentLoaded", init);
  document.addEventListener("htmx:afterSettle", init);

  window.raakRecordForm = {
    isDirty: function () { return isDirty(theForm()); },
    // The form's first state was taken: from here on a change is seen as one.
    ready: function () { var form = theForm(); return !!form && form.raakInitial !== undefined; },
    snapshot: snapshot,
    /* What the form holds for the fields with one of these names or a name
       that starts with one of these prefixes, as {name: [values]} — for a
       request beside the form that reads it as it stands (the Assistent's
       proposer, #1659). Nothing is validated: the form is not being saved. */
    valuesOf: function (names, prefixes) {
      var form = theForm();
      var values = {};
      if (!form) return values;
      Array.prototype.forEach.call(form.elements, function (el) {
        if (!el.name || el.disabled || el.tagName === "BUTTON" || el.type === "file") return;
        if ((el.type === "checkbox" || el.type === "radio") && !el.checked) return;
        var wanted = names.indexOf(el.name) !== -1 || prefixes.some(function (p) { return el.name.indexOf(p) === 0; });
        if (!wanted) return;
        (values[el.name] = values[el.name] || []).push(el.value);
      });
      return values;
    },
  };
})();
