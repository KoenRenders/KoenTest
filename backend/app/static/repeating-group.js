/* The repeating group of the kit (CR-11 block 7, #1559; design-system-end-state §3.3).
 *
 * Rows of a record form — dates, components with their products, organisers —
 * are added, removed, moved and duplicated IN THE PAGE. Nothing is sent until
 * the form's one "Opslaan"; "Annuleren" reloads the record, so everything done
 * here is undone by not saving. That is why removing a row asks nothing.
 *
 * The markup comes from `ui.repeating_group` and `ui.group_row`; this file reads
 * only their data attributes:
 *
 *   [data-repeating-group]    the group; `data-token` is the placeholder a new
 *                             row's key replaces in the group's <template>
 *   [data-group-rows]         the rows' parent
 *   [data-group-row]          one row; `data-row-key` is its key
 *   [data-group-add]          the "+ …" button of the group
 *   [data-row-action]         up | down | duplicate | remove, in the row's menu
 *   [data-row-handle]         the drag handle
 *   [data-row-title]          mirrors the value of the row's [data-row-title-source]
 *
 * One listener each on the document, so rows that arrive later — a new row, a
 * fragment htmx swapped in — need no wiring. No arrow function touches markup.
 */
(function () {
  "use strict";
  if (window.raakRepeatingGroup) return;
  var counter = 0;

  function newKey() {
    counter += 1;
    return "n" + Date.now().toString(36) + counter;
  }

  function rowsOf(group) {
    var holder = group.querySelector("[data-group-rows]");
    return Array.prototype.filter.call(holder.children, function (el) {
      return el.hasAttribute("data-group-row");
    });
  }

  function groupOf(row) {
    return row.parentElement.closest("[data-repeating-group]");
  }

  /* The state a group shows about its rows: the empty line, and which moves
     are possible (Omhoog is off on the first row, Omlaag on the last). */
  function refresh(group) {
    var rows = rowsOf(group);
    var empty = null;
    Array.prototype.forEach.call(group.children, function (el) {
      if (el.hasAttribute("data-group-empty")) empty = el;
    });
    if (empty) empty.hidden = rows.length > 0;
    var head = null;
    Array.prototype.forEach.call(group.children, function (el) {
      if (el.hasAttribute("data-group-head")) head = el;
    });
    if (head) head.hidden = rows.length === 0;
    rows.forEach(function (row, index) {
      setDisabled(row, "up", index === 0);
      setDisabled(row, "down", index === rows.length - 1);
    });
  }

  function ownMenuItem(row, action) {
    var items = row.querySelectorAll('[data-row-action="' + action + '"]');
    for (var i = 0; i < items.length; i++) {
      if (items[i].closest("[data-group-row]") === row) return items[i];
    }
    return null;
  }

  function setDisabled(row, action, off) {
    var item = ownMenuItem(row, action);
    if (item) item.disabled = off;
  }

  function focusFirst(row) {
    var field = row.querySelector(
      "input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled])"
    );
    if (field) field.focus();
  }

  function activate(node) {
    if (window.htmx) window.htmx.process(node);
  }

  /* "+ Datum": the group's template, its placeholder replaced by a fresh key,
     appended in place with the focus on its first field. */
  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function add(group, values) {
    var template = null;
    Array.prototype.forEach.call(group.children, function (el) {
      if (el.tagName === "TEMPLATE" && el.hasAttribute("data-group-template")) template = el;
    });
    if (!template) return null;
    var html = template.innerHTML.split(group.getAttribute("data-token")).join(newKey());
    // A picked row (an organiser from the member search) fills its own tokens.
    Object.keys(values || {}).forEach(function (token) {
      html = html.split(token).join(escapeHtml(values[token]));
    });
    var holder = group.querySelector("[data-group-rows]");
    holder.insertAdjacentHTML("beforeend", html);
    var row = rowsOf(group).pop();
    activate(row);
    refresh(group);
    focusFirst(row);
    return row;
  }

  var KEYED = ["name", "id", "for", "form", "aria-describedby", "aria-labelledby", "data-row-key", "data-token-owner"];

  /* Give `row` (a clone) a new key: every attribute that carries the old key
     as a whole segment — `c.12.name`, `c-12-name`, `p_order.12` — gets the new. */
  function rekey(row) {
    var old = row.getAttribute("data-row-key");
    var fresh = newKey();
    var pattern = new RegExp("(^|[.\\-_])" + old.replace(/[^\w]/g, "\\$&") + "(?=$|[.\\-_])", "g");
    var nodes = [row].concat(Array.prototype.slice.call(row.querySelectorAll("*")));
    nodes.forEach(function (el) {
      // The NAME of a row's own order field carries its PARENT's key
      // (`p_order.<component>`), not its own. A product 2 under a component 2
      // would otherwise rename that field to its own new key, and the server
      // would look for the component's products under a name nobody sent.
      var ownOrder = el.hasAttribute("data-row-order") && el.closest("[data-group-row]") === row;
      KEYED.forEach(function (attr) {
        if (ownOrder && attr === "name") return;
        var value = el.getAttribute(attr);
        if (value && value.indexOf(old) !== -1) {
          el.setAttribute(attr, value.replace(pattern, "$1" + fresh));
        }
      });
      if (el.tagName === "INPUT" && el.type === "hidden" && el.hasAttribute("data-row-order") && el.value === old) {
        el.value = fresh;
      }
      if (el.tagName === "TEMPLATE") {
        el.innerHTML = el.innerHTML.replace(pattern, "$1" + fresh);
      }
    });
    row.setAttribute("data-row-key", fresh);
  }

  /* A copy of the row under it, with what is typed in it; a component takes
     its products along. Files are not copied: a file input cannot be filled. */
  function duplicate(row) {
    var copy = row.cloneNode(true);
    var source = row.querySelectorAll("input, select, textarea");
    var target = copy.querySelectorAll("input, select, textarea");
    for (var i = 0; i < source.length; i++) {
      if (source[i].type === "file") continue;
      if (source[i].type === "checkbox" || source[i].type === "radio") target[i].checked = source[i].checked;
      else target[i].value = source[i].value;
    }
    // Innermost first, so a nested row's key is replaced before its parent's.
    var nested = Array.prototype.slice.call(copy.querySelectorAll("[data-group-row]")).reverse();
    nested.forEach(rekey);
    rekey(copy);
    // An existing record's row menu is closed in the copy.
    Array.prototype.forEach.call(copy.querySelectorAll("[data-row-menu]"), function (menu) {
      menu.style.display = "none";
    });
    row.insertAdjacentElement("afterend", copy);
    activate(copy);
    refresh(groupOf(copy));
    focusFirst(copy);
    return copy;
  }

  function move(row, direction) {
    var group = groupOf(row);
    var rows = rowsOf(group);
    var index = rows.indexOf(row);
    var other = rows[index + (direction === "up" ? -1 : 1)];
    if (!other) return;
    if (direction === "up") row.parentElement.insertBefore(row, other);
    else row.parentElement.insertBefore(other, row);
    refresh(group);
    var trigger = row.querySelector("[data-row-menu-trigger]");
    if (trigger) trigger.focus();
  }

  function remove(row) {
    var group = groupOf(row);
    var rows = rowsOf(group);
    var index = rows.indexOf(row);
    row.remove();
    refresh(group);
    var next = rows[index + 1] || rows[index - 1];
    var target = next ? next.querySelector("[data-row-menu-trigger]") : group.querySelector("[data-group-add]");
    if (target) target.focus();
    group.dispatchEvent(new CustomEvent("row-removed", { bubbles: true }));
  }

  document.addEventListener("click", function (event) {
    var addButton = event.target.closest("[data-group-add]");
    if (addButton) {
      event.preventDefault();
      add(addButton.closest("[data-repeating-group]"));
      return;
    }
    var pick = event.target.closest("[data-group-pick]");
    if (pick) {
      event.preventDefault();
      var name = pick.getAttribute("data-group-pick");
      var scope = pick.closest("form") || document;
      var target = scope.querySelector('[data-repeating-group="' + name + '"]');
      if (target) add(target, JSON.parse(pick.getAttribute("data-pick") || "{}"));
      var picked = pick.closest("[data-pick-item]");
      if (picked) picked.remove(); // not offered twice
      return;
    }
    var item = event.target.closest("[data-row-action]");
    if (!item || item.disabled) return;
    event.preventDefault();
    var row = item.closest("[data-group-row]");
    var action = item.getAttribute("data-row-action");
    if (action === "up" || action === "down") move(row, action);
    else if (action === "duplicate") duplicate(row);
    else if (action === "remove") remove(row);
  });

  /* The title line of a composite item follows its name field. */
  document.addEventListener("input", function (event) {
    var source = event.target.closest("[data-row-title-source]");
    if (!source) return;
    var row = source.closest("[data-group-row]");
    var title = row && row.querySelector("[data-row-title]");
    if (title && title.closest("[data-group-row]") === row) {
      title.textContent = source.value || title.getAttribute("data-row-title") || "";
    }
  });

  /* ── Dragging by the handle ───────────────────────────────────────────────
     The row is draggable only while its handle is held, so a text selection in
     a field never starts a drag. The origin stays as a dotted space, the drop
     place is a brand line; Escape ends an HTML drag without a drop, and the
     rows are back as they were. */
  var dragged = null;
  var origin = null;
  var dropped = false;

  document.addEventListener("pointerdown", function (event) {
    var handle = event.target.closest("[data-row-handle]");
    if (handle) handle.closest("[data-group-row]").setAttribute("draggable", "true");
  });
  document.addEventListener("pointerup", function () {
    Array.prototype.forEach.call(document.querySelectorAll("[data-group-row][draggable]"), function (row) {
      if (row !== dragged) row.removeAttribute("draggable");
    });
  });

  function clearMarks() {
    Array.prototype.forEach.call(document.querySelectorAll(".group-drop-before, .group-drop-after"), function (el) {
      el.classList.remove("group-drop-before", "group-drop-after");
    });
  }

  document.addEventListener("dragstart", function (event) {
    var row = event.target.closest && event.target.closest("[data-group-row][draggable]");
    if (!row || event.target !== row) return;
    dragged = row;
    dropped = false;
    origin = { parent: row.parentElement, next: row.nextElementSibling };
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", row.getAttribute("data-row-key"));
    row.classList.add("group-dragging");
  });

  function target(event) {
    if (!dragged) return null;
    var row = event.target.closest && event.target.closest("[data-group-row]");
    while (row && row.parentElement !== dragged.parentElement) {
      row = row.parentElement.closest("[data-group-row]");
    }
    return row && row !== dragged ? row : null;
  }

  document.addEventListener("dragover", function (event) {
    var row = target(event);
    if (!row) return;
    event.preventDefault();
    clearMarks();
    var box = row.getBoundingClientRect();
    row.classList.add(event.clientY < box.top + box.height / 2 ? "group-drop-before" : "group-drop-after");
  });

  document.addEventListener("drop", function (event) {
    var row = target(event);
    if (!row) return;
    event.preventDefault();
    var before = row.classList.contains("group-drop-before");
    row.parentElement.insertBefore(dragged, before ? row : row.nextElementSibling);
    dropped = true;
  });

  document.addEventListener("dragend", function (event) {
    if (!dragged) return;
    if (!dropped && origin) {
      origin.parent.insertBefore(dragged, origin.next); // Escape, or dropped nowhere
    }
    dragged.classList.remove("group-dragging");
    dragged.removeAttribute("draggable");
    clearMarks();
    refresh(groupOf(dragged));
    dragged = null;
    origin = null;
  });

  function refreshAll(root) {
    Array.prototype.forEach.call((root || document).querySelectorAll("[data-repeating-group]"), refresh);
  }
  document.addEventListener("DOMContentLoaded", function () { refreshAll(); });
  document.addEventListener("htmx:afterSettle", function (event) { refreshAll(event.target.parentElement || document); });

  window.raakRepeatingGroup = { add: add, duplicate: duplicate, move: move, remove: remove, refresh: refreshAll };
})();
