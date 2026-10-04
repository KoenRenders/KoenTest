/* A proposal for the form (CR-11 block 10, #1562; design-system-end-state §3.15).
 *
 * The Assistent proposes values for fields of the screen beside it. A proposal
 * is field names + values + the value each field had when the proposal was
 * asked (its BASE). Nothing is written by a proposal:
 *
 *   offered   the fields it touches get a blue line, the brand tint and the note
 *             "Voorstel · nog niet toegepast"; the panel says "n velden ingevuld
 *             als voorstel" with Toepassen / Negeren;
 *   applied   Toepassen puts the values INTO THE FORM — never into the database:
 *             the form's own save (the action bar, or the autosave of a document)
 *             is the only thing that writes;
 *   skipped   a field that no longer holds its base was changed meanwhile: it is
 *             left alone and named. A proposal never overwrites in silence;
 *   dismissed Negeren takes the marks away.
 *
 * The markup comes from `ui.form_proposal` (the block in the panel) and from the
 * fields of the screen, which this file finds by `[data-field="<name>"]`. A
 * block with `data-proposal-apply-url` asks the server for its final values on
 * Toepassen (the newsletter: which marked passages are kept), and the answer is
 * a block with `data-proposal-auto` that is applied as it arrives.
 */
(function () {
  "use strict";
  if (window.raakFormProposal) return;

  function fieldOf(name) {
    return document.querySelector('[data-field="' + window.CSS.escape(name) + '"]');
  }

  function editorOf(field) {
    var trix = field.querySelector("trix-editor");
    return trix && trix.editor ? trix : null;
  }

  function controlOf(field) {
    return field.querySelector("input:not([type=hidden]):not([type=file]), select, textarea");
  }

  /* What the field holds now, as the server would receive it. */
  function read(field) {
    var trix = editorOf(field);
    if (trix) return trix.inputElement ? trix.inputElement.value : trix.innerHTML;
    var control = controlOf(field);
    return control ? control.value : "";
  }

  function same(a, b) {
    return String(a == null ? "" : a).trim() === String(b == null ? "" : b).trim();
  }

  /* Through the control itself, so everything that listens — the changed-or-not
     of a record form, the autosave of a document, a counter, a growing field,
     the editor's undo — hears it as if it was typed. */
  function write(field, value, item) {
    var trix = editorOf(field);
    if (trix) {
      // A rich text takes the value where the proposal says: over everything
      // (the default), over the selection it was asked for, or at the cursor —
      // the editor remembers where that stood, also after a click in the panel.
      trix.editor.recordUndoEntry("Assistent");
      if (item.placement === "selection" && item.range && item.range.length === 2) {
        trix.editor.setSelectedRange(item.range);
      } else if (item.placement !== "cursor") {
        trix.editor.setSelectedRange([0, trix.editor.getDocument().getLength()]);
      }
      trix.editor.insertHTML(value);
      trix.focus();
      return;
    }
    var control = controlOf(field);
    if (!control) return;
    control.value = value;
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function fieldsOf(block) {
    var data = block.querySelector("[data-proposal-fields]");
    try {
      return data ? JSON.parse(data.textContent) : [];
    } catch (error) {
      return [];
    }
  }

  function note(field, state, text) {
    var old = field.querySelector("[data-proposal-note]");
    if (old) old.remove();
    field.removeAttribute("data-proposed");
    field.removeAttribute("data-proposal-applied");
    if (!state) return;
    field.setAttribute(state === "applied" ? "data-proposal-applied" : "data-proposed", "");
    var p = document.createElement("p");
    p.setAttribute("data-proposal-note", state);
    p.textContent = text;
    field.appendChild(p);
  }

  function clearOffered() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-field][data-proposed]"), function (field) {
      note(field, null);
    });
  }

  function finish(block, text) {
    var actions = block.querySelector("[data-proposal-actions]");
    if (actions) actions.hidden = true;
    Array.prototype.forEach.call(block.querySelectorAll("input, button"), function (el) {
      if (el.closest("[data-proposal-actions]") || el.type === "checkbox") el.disabled = true;
    });
    var result = block.querySelector("[data-proposal-result]");
    if (result) {
      result.textContent = text;
      result.hidden = false;
    }
    block.setAttribute("data-proposal-state", "closed");
  }

  /* Show a proposal on its fields. An older one that was never applied gives way. */
  function offer(block) {
    if (block.raakOffered) return;
    block.raakOffered = true;
    clearOffered();
    Array.prototype.forEach.call(document.querySelectorAll('[data-form-proposal][data-proposal-state="open"]'), function (other) {
      if (other !== block) finish(other, other.dataset.wordReplaced || "");
    });
    block.setAttribute("data-proposal-state", "open");
    fieldsOf(block).forEach(function (item) {
      var field = fieldOf(item.name);
      if (field) note(field, "proposed", block.dataset.wordProposed || "");
    });
  }

  function apply(block) {
    var applied = [];
    var skipped = [];
    fieldsOf(block).forEach(function (item) {
      var field = fieldOf(item.name);
      if (!field) return;
      // Without a base the server already refused a stale proposal itself
      // (a rich text: its stored form is not the editor's, letter for letter).
      if (item.base !== undefined && item.base !== null && !same(read(field), item.base)) {
        note(field, null);
        skipped.push(item.label || item.name);
        return;
      }
      write(field, item.value, item);
      note(field, "applied", block.dataset.wordApplied || "");
      applied.push(item.label || item.name);
    });
    var text = ((applied.length === 1 ? block.dataset.wordDoneOne : block.dataset.wordDoneMany) || "").replace("{n}", applied.length);
    if (skipped.length) {
      text += " " + ((skipped.length === 1 ? block.dataset.wordSkippedOne : block.dataset.wordSkippedMany) || "")
        .replace("{n}", skipped.length)
        .replace("{fields}", skipped.join(", "));
    }
    finish(block, text.trim());
    block.dispatchEvent(new CustomEvent("proposal:applied", { bubbles: true, detail: { applied: applied, skipped: skipped } }));
    return { applied: applied, skipped: skipped };
  }

  function dismiss(block) {
    fieldsOf(block).forEach(function (item) {
      var field = fieldOf(item.name);
      if (field && field.hasAttribute("data-proposed")) note(field, null);
    });
    finish(block, block.dataset.wordDismissed || "");
    // A screen that keeps its conversation hears that this one was set aside.
    var url = block.getAttribute("data-proposal-dismiss-url");
    if (url) window.htmx.ajax("POST", url, { source: block, swap: "none" });
  }

  document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-proposal-apply], [data-proposal-dismiss]");
    if (!button) return;
    var block = button.closest("[data-form-proposal]");
    if (!block || block.getAttribute("data-proposal-state") !== "open") return;
    if (button.hasAttribute("data-proposal-dismiss")) {
      dismiss(block);
      return;
    }
    var url = block.getAttribute("data-proposal-apply-url");
    if (!url) {
      apply(block);
      return;
    }
    // The server decides the final values (which marked passages are kept); its
    // answer replaces this block and is applied as it arrives.
    // `data-proposal-include`: fields of the screen the server needs to decide
    // (the newsletter's text as it stands in the editor).
    var values = window.htmx.values(block);
    var include = block.getAttribute("data-proposal-include");
    if (include) {
      Array.prototype.forEach.call(document.querySelectorAll(include), function (el) {
        if (el.name) values[el.name] = el.value;
      });
    }
    window.htmx.ajax("POST", url, { source: block, target: block, swap: "outerHTML transition:false", values: values });
  });

  function scan(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll("[data-form-proposal]"), function (block) {
      if (block.raakOffered) return;
      if (block.hasAttribute("data-proposal-auto")) {
        block.raakOffered = true;
        block.setAttribute("data-proposal-state", "open");
        apply(block);
      } else if (block.getAttribute("data-proposal-state") !== "closed") {
        offer(block);
      }
    });
  }
  document.addEventListener("DOMContentLoaded", function () { scan(); });
  document.addEventListener("htmx:afterSettle", function () { scan(); });

  window.raakFormProposal = { offer: offer, apply: apply, dismiss: dismiss, scan: scan };
})();
