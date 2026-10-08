/* The document editor of the kit (CR-17 #1671, slice 2; figure and dialogs
 * in slice 3).
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
 * The dialogs the toolbar opens live in the MACRO as well (slice 3): the
 * figure dialog (the kit's media picker, the alternative text, the caption
 * and the placement) and the link dialog (B5: the browser's `prompt` is a
 * browser dialog, and the UI norm has none). This file only announces
 * (`raak-figure-choose`, `raak-link-edit`) and applies
 * (`raak-figure-chosen`, `raak-link-save`); the words and the chrome stay
 * with the kit's markup. The editor's id travels in every event, so two
 * editors on one page never hear each other's dialogs.
 */
(function () {
  "use strict";
  /* The run-once guard, SET here (the review's B2, #1734): the macro puts
     this file in swapped content, so a boosted visit or a refused save
     executes her again — without the flag every run added another set of
     document listeners for the dialogs. */
  if (window.raakDocumentEditor) return;
  window.raakDocumentEditor = true;

  /* The toolbar's chrome lives in the editor's own CSS
     (`tiptap-3.31.4.css`), like Trix's `trix.css` styles the toolbar
     `trix.js` builds — NOT in Tailwind: build-css.sh scans templates, and
     markup a script injects must not depend on a class that happens to be
     generated because some template uses her. Semantic names, kit tokens. */

  /* Every editor on the page, by her id — the dialogs' events name the
     editor they mean, so two editors never write into each other. */
  var editors = {};

  function announce(name, detail) {
    /* bubbles: the dialogs listen on the window (Alpine's `.window`), and a
       CustomEvent without bubbles never leaves the document she was
       dispatched on — measured on the kit page: the link dialog stayed
       closed until she bubbles. */
    document.dispatchEvent(new CustomEvent(name, { detail: detail, bubbles: true }));
  }

  function button(label, aria) {
    var el = document.createElement("button");
    el.type = "button";
    el.className = "de-btn";
    el.textContent = label;
    if (aria) el.setAttribute("aria-label", aria);
    /* An editor toolbar never takes the focus her clicks steal: with the
       default behaviour the button holds the focus and the author's first
       keystrokes go nowhere (measured on CI: "Kopregel" arrived as
       "pregel", #1699). preventDefault on mousedown keeps the editor
       focused; the click itself still fires. */
    el.addEventListener("mousedown", function (event) {
      event.preventDefault();
    });
    return el;
  }

  /* The figure: the block the set offers, in the shape the server's schema
     knows (media id, placement, caption). The author chooses her picture
     in the dialog (the kit's picker); here she renders with her image, in
     the same classes the site's renderer writes — `prose-figures.css` is
     ONE source for both, so the author sees the placement the visitor
     gets (the parity #1230 guarded for the Trix sizes). The data
     attributes carry the figure through a copy inside the editor:
     ProseMirror serialises her to this markup and parses her back, and
     without them a pasted figure would lose her picture. */
  function figureNode(RaakTiptap, config, label) {
    var mediaUrl = (config.figure && config.figure.mediaUrl) || "";
    return RaakTiptap.Node.create({
      name: "figure",
      group: "block",
      atom: true,
      addAttributes: function () {
        return {
          media_id: { default: 0 },
          alt: { default: null },
          placement: { default: null },
          caption: { default: null },
          width: { default: null },
          height: { default: null },
        };
      },
      parseHTML: function () {
        return [
          {
            tag: "figure[data-document-figure]",
            getAttrs: function (el) {
              return {
                media_id: Number(el.getAttribute("data-media-id")) || 0,
                alt: el.getAttribute("data-alt") || null,
                placement: el.getAttribute("data-placement") || null,
                caption: el.getAttribute("data-caption") || null,
                width: Number(el.getAttribute("data-width")) || null,
                height: Number(el.getAttribute("data-height")) || null,
              };
            },
          },
        ];
      },
      renderHTML: function (props) {
        var a = props.node.attrs;
        var placement = a.placement || "full";
        var attrs = {
          "data-document-figure": "",
          "data-media-id": String(a.media_id || 0),
          "data-placement": placement,
          "data-alt": a.alt || "",
          "data-caption": a.caption || "",
          "data-width": a.width || "",
          "data-height": a.height || "",
          class: "prose-figure prose-figure--" + placement,
        };
        if (!a.media_id) {
          /* Never through the dialog (she refuses to insert without a
             picture), but an honest rendering beats a broken one: the
             dashed placeholder box, so the author sees a block. */
          attrs.class += " de-figure-empty";
          return ["figure", attrs, label];
        }
        var img = { src: mediaUrl + a.media_id, alt: a.alt || "" };
        if (a.width) img.width = a.width;
        if (a.height) img.height = a.height;
        var children = [["img", img]];
        if (a.caption) children.push(["figcaption", {}, a.caption]);
        return ["figure", attrs].concat(children);
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

  function toolbar(editor, config, editorId) {
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
          /* B5 (review of #1699): the link dialog of the macro, never the
             browser's prompt — the UI norm has no browser dialogs. The
             current href travels along, so the author edits her link
             instead of retyping her. */
          announce("raak-link-edit", {
            editor: editorId,
            href: editor.getAttributes("link").href || "",
          });
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
      summary.addEventListener("mousedown", function (event) {
        event.preventDefault();
      });
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
          } else if (config.figure) {
            /* The figure never lands without her picture: the dialog of
               the macro opens the kit's picker, and the server's shape
               gate refuses a document that saves such a figure anyway. */
            announce("raak-figure-choose", { editor: editorId });
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

  /* The dialogs answer here: the macro's markup collects the choice and
     names this editor; the insert lands where the author was writing. */
  document.addEventListener("raak-figure-chosen", function (event) {
    var editor = editors[event.detail.editor];
    if (!editor || editor.isDestroyed) return;
    var choice = event.detail;
    editor
      .chain()
      .focus()
      .insertContent({
        type: "figure",
        attrs: {
          media_id: choice.media_id,
          alt: choice.alt,
          caption: choice.caption || null,
          placement: choice.placement || null,
          width: choice.width || null,
          height: choice.height || null,
        },
      })
      .run();
  });

  document.addEventListener("raak-link-save", function (event) {
    var editor = editors[event.detail.editor];
    if (!editor || editor.isDestroyed) return;
    var url = event.detail.url || "";
    if (url === "") {
      /* The author emptied the field: the link goes, the words stay. */
      editor.chain().focus().extendMarkRange("link").unsetLink().run();
    } else {
      editor.chain().focus().extendMarkRange("link").setLink({ href: url }).run();
    }
  });

  function build(mount) {
    if (mount.dataset.ready) return;
    mount.dataset.ready = "1";
    var RaakTiptap = window.RaakTiptap;
    var config = {};
    try {
      config = JSON.parse(mount.dataset.config || "{}");
    } catch (error) {
      /* Developer copy, not the author's: a broken configuration is a
         bug in the screen that rendered it, so English (review C, #1699). */
      mount.textContent = "The editor configuration is not valid JSON.";
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
        /* Off, so the editor cannot write what the server refuses (review
           B1, #1699): the page set has no quote, code, code block, rule or
           underline — a typed or pasted one would become a document the
           schema refuses with "Onbekend blok". They come back when a set
           offers them. */
        blockquote: false,
        code: false,
        codeBlock: false,
        horizontalRule: false,
        underline: false,
      }),
    ];
    if ((config.insert || []).indexOf("table") !== -1) {
      extensions.push(RaakTiptap.TableKit.configure({ table: { resizable: false } }));
    }
    var figureLabel = "";
    (config.toolbar.insert || []).forEach(function (item) {
      if (item.id === "figure") figureLabel = item.label;
    });
    if ((config.insert || []).indexOf("figure") !== -1) {
      extensions.push(figureNode(RaakTiptap, config, figureLabel));
    }

    var editor = new RaakTiptap.Editor({
      element: surface,
      extensions: extensions,
      content: input && input.value ? JSON.parse(input.value) : "",
    });
    editors[mount.id] = editor;
    if (input) {
      /* Only a real edit writes: the editor's start is the server's own
         document, already in the input — writing her again would mark the
         screen changed before the author touched a key (slice 3, the
         review's "hidden input" note on #1699). */
      editor.on("update", function () {
        input.value = JSON.stringify(editor.getJSON());
      });
    }
    mount.insertBefore(toolbar(editor, config, mount.id), surface);
  }

  function scan() {
    document.querySelectorAll("[data-document-editor]").forEach(build);
  }
  document.addEventListener("DOMContentLoaded", scan);
  document.addEventListener("htmx:afterSwap", scan);
})();
