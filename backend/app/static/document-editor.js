/* The document editor of the kit (CR-17 #1671, slice 2).
 *
 * TipTap, loaded from /static/vendor/ (vendored and pinned; the checksum
 * stands in scripts/vendor-manifest.txt). This file builds every editor on
 * the page from the configuration the server sent along — the markup comes
 * from the `ui.document_editor` macro and carries two data attributes:
 *
 *   [data-document-editor]   the mount point; `data-input` names the hidden
 *                            input that holds the document's JSON,
 *                            `data-config` the set's configuration from
 *                            `cms.api.schema_for("page")`.
 *
 * The toolbar is BUILT here, from that configuration — never hand-written
 * in a domain template (C6 3, gate 14 widened): a template that writes its
 * own toolbar is the third copy of the editor, and this file is the one
 * place the editor exists. The words on the buttons come from the
 * configuration too (UI copy is the server's, like the macro's).
 *
 * What is deliberately NOT here (yet): the media picker for a figure —
 * slice 3 wires CR-15's picker; until then the insert menu places a figure
 * atom with no image (the placeholder box), and the server's shape gate
 * refuses a document that saves such a figure without her media id.
 */
(function () {
  "use strict";
  if (window.raakDocumentEditor) return;

  /* The toolbar's chrome lives in the editor's own CSS
     (`tiptap-3.31.4.css`), like Trix's `trix.css` styles the toolbar
     `trix.js` builds — NOT in Tailwind: build-css.sh scans templates, and
     markup a script injects must not depend on a class that happens to be
     generated because some template uses her. Semantic names, kit tokens. */

  function button(label, aria) {
    var el = document.createElement("button");
    el.type = "button";
    el.className = "de-btn";
    el.textContent = label;
    if (aria) el.setAttribute("aria-label", aria);
    return el;
  }

  /* The figure atom: the block the set offers, in the shape the server's
     schema knows (media_id, placement, caption). No image yet — slice 3. */
  function figureNode(RaakTiptap) {
    return RaakTiptap.Node.create({
      name: "figure",
      group: "block",
      atom: true,
      addAttributes: function () {
        return {
          media_id: { default: 0 },
          placement: { default: null },
          caption: { default: null },
          alt: { default: null },
        };
      },
      parseHTML: function () {
        return [{ tag: "figure[data-figure]" }];
      },
      renderHTML: function (props) {
        var attrs = { "data-figure": "" };
        var caption = props.node.attrs.caption || props.node.attrs.alt || "";
        return ["figure", attrs, "Afbeelding" + (caption ? ": " + caption : "")];
      },
    });
  }

  function markCommand(id) {
    if (id === "bold") return { command: "toggleBold", active: "bold" };
    if (id === "italic") return { command: "toggleItalic", active: "italic" };
    if (id === "strike") return { command: "toggleStrike", active: "strike" };
    if (id === "link") return { command: "toggleLink", active: "link" };
    return null;
  }

  function listCommand(id) {
    if (id === "bulletList") return { command: "toggleBulletList", active: "bulletList" };
    if (id === "orderedList") return { command: "toggleOrderedList", active: "orderedList" };
    return null;
  }

  function toolbar(editor, config) {
    var bar = document.createElement("div");
    bar.className = "de-bar";
    var press = [];

    config.headings.forEach(function (heading) {
      var el = button(heading.label);
      el.addEventListener("click", function () {
        editor.chain().focus().toggleHeading({ level: heading.level }).run();
      });
      press.push({
        el: el,
        isOn: function () {
          return editor.isActive("heading", { level: heading.level });
        },
      });
      bar.appendChild(el);
    });

    (config.toolbar.marks || []).forEach(function (mark) {
      var cmd = markCommand(mark.id);
      if (!cmd) return;
      var symbol = mark.id === "bold" ? "B" : mark.id === "italic" ? "I" : mark.id === "strike" ? "S" : "";
      /* A letter is the word of its mark (B/I/S) and needs her aria-label;
         the link says what she is — "L" would read as a letter (§2.12: a
         button describes the action). */
      var el = button(symbol || mark.label, symbol ? mark.label : null);
      el.addEventListener("click", function () {
        if (mark.id === "link") {
          var href = editor.getAttributes("link").href || "";
          var url = window.prompt(mark.label + " (https://…)", href);
          if (url === null) return;
          if (url === "") {
            editor.chain().focus().unsetLink().run();
          } else {
            editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
          }
        } else {
          editor.chain().focus()[cmd.command]().run();
        }
      });
      press.push({
        el: el,
        isOn: function () {
          return editor.isActive(cmd.active);
        },
      });
      bar.appendChild(el);
    });

    (config.toolbar.lists || []).forEach(function (list) {
      var cmd = listCommand(list.id);
      if (!cmd) return;
      var symbol = list.id === "bulletList" ? "•" : "1.";
      var el = button(symbol, list.label);
      el.addEventListener("click", function () {
        editor.chain().focus()[cmd.command]().run();
      });
      press.push({
        el: el,
        isOn: function () {
          return editor.isActive(cmd.active);
        },
      });
      bar.appendChild(el);
    });

    var insertable = (config.toolbar.insert || []).filter(function (item) {
      return item.id === "table" || item.id === "figure";
    });
    if (insertable.length) {
      var menu = document.createElement("details");
      menu.className = "de-menu";
      var summary = document.createElement("summary");
      summary.className = "de-btn de-menu-toggle";
      summary.textContent = config.toolbar.insertMenu + " ▾";
      menu.appendChild(summary);
      var items = document.createElement("div");
      items.className = "de-menu-items";
      insertable.forEach(function (item) {
        var el = button(item.label, item.label);
        el.className = "de-btn de-menu-item";
        el.addEventListener("click", function () {
          menu.removeAttribute("open");
          if (item.id === "table") {
            editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
          } else {
            /* The picker arrives with slice 3 (#1671); the atom carries no
               image yet and the server refuses her without a media id. */
            editor.chain().focus().insertContent({ type: "figure", attrs: { media_id: 0 } }).run();
          }
        });
        items.appendChild(el);
      });
      menu.appendChild(items);
      bar.appendChild(menu);
    }

    editor.on("selectionUpdate", function () {
      press.forEach(function (state) {
        if (state.isOn()) {
          state.el.classList.add("is-on");
          state.el.setAttribute("aria-pressed", "true");
        } else {
          state.el.classList.remove("is-on");
          state.el.setAttribute("aria-pressed", "false");
        }
      });
    });
    return bar;
  }

  function build(mount) {
    if (mount.dataset.ready) return;
    mount.dataset.ready = "1";
    var RaakTiptap = window.RaakTiptap;
    var config = {};
    try {
      config = JSON.parse(mount.dataset.config || "{}");
    } catch (error) {
      mount.textContent = "De editor-configuratie is geen JSON.";
      return;
    }
    var input = document.getElementById(mount.dataset.input);
    var surface = document.createElement("div");
    surface.className = "de-surface cms-content";
    mount.appendChild(surface);

    var extensions = [
      RaakTiptap.StarterKit.configure({
        heading: { levels: config.headings.map(function (h) { return h.level; }) },
        strike: (config.marks || []).indexOf("strike") !== -1,
        link: (config.marks || []).indexOf("link") !== -1,
        bulletList: (config.lists || []).indexOf("bulletList") !== -1,
        orderedList: (config.lists || []).indexOf("orderedList") !== -1,
      }),
    ];
    if ((config.insert || []).indexOf("table") !== -1) {
      extensions.push(RaakTiptap.TableKit.configure({ table: { resizable: false } }));
    }
    if ((config.insert || []).indexOf("figure") !== -1) {
      extensions.push(figureNode(RaakTiptap));
    }

    var editor = new RaakTiptap.Editor({
      element: surface,
      extensions: extensions,
      content: input && input.value ? JSON.parse(input.value) : "",
    });
    if (input) {
      var write = function () {
        input.value = JSON.stringify(editor.getJSON());
      };
      editor.on("update", write);
      write();
    }
    mount.insertBefore(toolbar(editor, config), surface);
  }

  function scan() {
    document.querySelectorAll("[data-document-editor]").forEach(build);
  }
  document.addEventListener("DOMContentLoaded", scan);
  document.addEventListener("htmx:afterSwap", scan);
})();
