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
  /* The columns of #1679 (C4.13): two sub-documents of equal width; the
     stored `align` is derived by the server's save adapter, so the editor
     writes "top" and lets the adapter decide. The phone's stack order is
     the site's (css); the editor shows the grid of the two columns. */
  function columnsNode(RaakTiptap) {
    var columns = RaakTiptap.Node.create({
      name: "columns",
      group: "block",
      /* ProseMirror knows no `{1,2}` count in her content expressions —
         the SERVER's schema holds the pair ({1,2}, cms/schema.py); the editor
         takes "one or more" and the adapter plus the validator keep her
         honest on what is stored. */
      content: "column+",
      addAttributes: function () {
        return { align: { default: "top" } };
      },
      parseHTML: function () {
        return [{ tag: "div.prose-columns" }];
      },
      renderHTML: function (props) {
        var cls = "prose-columns";
        if (props.node.attrs.align === "middle") cls += " prose-columns--middle";
        return ["div", { class: cls }, 0];
      },
    });
    var column = RaakTiptap.Node.create({
      name: "column",
      content: "block+",
      parseHTML: function () {
        return [{ tag: "div.prose-column" }];
      },
      renderHTML: function () {
        return ["div", { class: "prose-column" }, 0];
      },
    });
    return [columns, column];
  }

  /* The button of #1679: her label and her variant, and the ONE
     destination she leads to — chosen in the dialog of the macro, which
     carries the pages and forms of the tenant (Koen, 11 October 2026:
     a page, an outside address, a form, and Lid worden). An atom: the
     author edits her through the dialog, not by typing. */
  function buttonNode(RaakTiptap, config) {
    return RaakTiptap.Node.create({
      name: "button",
      group: "block",
      atom: true,
      addAttributes: function () {
        return {
          label: { default: "" },
          variant: { default: "secondary" },
          page_id: { default: null },
          href: { default: null },
          form_slug: { default: null },
          screen: { default: null },
        };
      },
      parseHTML: function () {
        return [{ tag: "a[data-button]" }];
      },
      renderHTML: function (props) {
        var a = props.node.attrs;
        var naam = a.label || (config.toolbar.insert || []).filter(function (i) { return i.id === "button"; })[0].label;
        return ["a", { "data-button": "", class: "prose-button prose-button--" + (a.variant || "secondary") }, naam];
      },
    });
  }

  /* The callout of #1679 (C4.13): text only, typed in her box — an
     inline* node, like a paragraph with her own look. */
  function calloutNode(RaakTiptap) {
    return RaakTiptap.Node.create({
      name: "callout",
      group: "block",
      content: "inline*",
      parseHTML: function () {
        return [{ tag: "div.prose-callout" }];
      },
      renderHTML: function () {
        return ["div", { class: "prose-callout" }, 0];
      },
    });
  }

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
      return (
        item.id === "table" ||
        item.id === "figure" ||
        item.id === "columns" ||
        item.id === "button" ||
        item.id === "callout"
      );
    });
    if (insertable.length) {
      var menu = document.createElement("details");
      /* Her own class next to the table menu's (phase 2, #1679): the two
         menus share `.de-menu`, and a test or a screen that means one of
         them names her — `details.de-menu-insert`, never "the summary". */
      menu.className = "de-menu de-menu-insert";
      var summary = document.createElement("summary");
      summary.className = "de-btn de-menu-toggle";
      summary.textContent = config.toolbar.insertMenu + " ▾";
      summary.addEventListener("mousedown", function (event) {
        event.preventDefault();
      });
      menu.appendChild(summary);
      var items = document.createElement("div");
      items.className = "de-menu-items";
      var kolommen_el = null;
      insertable.forEach(function (item) {
        var el = button(item.label, item.label);
        el.className = "de-btn de-menu-item";
        if (item.id === "columns") kolommen_el = el;
        el.addEventListener("click", function () {
          menu.removeAttribute("open");
          if (item.id === "table") {
            editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
          } else if (item.id === "columns") {
            editor.chain().focus().insertContent({
              type: "columns",
              attrs: { align: "top" },
              content: [
                { type: "column", content: [{ type: "paragraph" }] },
                { type: "column", content: [{ type: "paragraph" }] },
              ],
            }).run();
          } else if (item.id === "callout") {
            editor.chain().focus().insertContent({ type: "callout" }).run();
          } else if (item.id === "button") {
            /* The button never lands without her destination: the dialog
               of the macro carries the pages and forms of the tenant, and
               the server refuses a button with no destination anyway
               (the shape rule, C6 2). With a button selected her own
               words and position travel along (review A1): the dialog
               opens showing what she holds, and Invoegen changes her at
               her own place. */
            var attrs_here = editor.getAttributes("button");
            var gekozen =
              attrs_here && attrs_here.label !== undefined
                ? editor.state.selection.from
                : null;
            announce("raak-button-choose", {
              editor: editorId,
              attrs: attrs_here && attrs_here.label !== undefined ? attrs_here : null,
              pos: gekozen,
            });
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
      menu.addEventListener("toggle", function () {
        if (menu.open) {
          /* "Kolommen" is not offered inside a column (review S3 of 12
             October 2026): the editor would insert the nested block and
             the save would refuse her — the menu offers what the save
             takes. The last click inside the editor tells where the
             author means: the browser commits a clicked position to the
             selection only a moment after the click, and that moment is
             not deterministic. Until the first click the selection speaks
             (the keyboard-only author), and the ancestors are asked by
             hand (`isActive` answers the selection's own node). The
             display goes on the style and not on the `hidden` attribute:
             the editor's own css sets `display` on `.de-btn`, and an
             attribute loses from her. */
          if (kolommen_el) {
            var inKolom = false;
            var klik = editor.laatsteKlik;
            var bron = editor.state.selection.$from;
            if (klik !== null && klik !== undefined) {
              try {
                bron = editor.state.doc.resolve(klik);
              } catch (error) {
                bron = editor.state.selection.$from;
              }
            }
            for (var d = bron.depth; d >= 1; d--) {
              if (bron.node(d).type.name === "column") {
                inKolom = true;
                break;
              }
            }
            kolommen_el.style.display = inKolom ? "none" : "";
          }
          openInRoom(menu, items);
        }
      });
      bar.appendChild(menu);
    }

    /* The table menu (CR-17 phase 2, #1679): the commands of C4.13 — the
       header row the author's own, rows and columns added and removed. The
       words come from the configuration like every word the editor shows;
       the menu is hidden until the cursor stands in a table (the commands
       refuse outside one, so showing her there would offer buttons that do
       nothing). */
    var tableMenu = config.toolbar.tableMenu;
    if (tableMenu) {
      var tmenu = document.createElement("details");
      tmenu.className = "de-menu de-menu-table";
      tmenu.hidden = true;
      var tsummary = document.createElement("summary");
      tsummary.className = "de-btn de-menu-toggle";
      tsummary.textContent = tableMenu.label + " ▾";
      tsummary.addEventListener("mousedown", function (event) {
        event.preventDefault();
      });
      tmenu.appendChild(tsummary);
      var titems = document.createElement("div");
      titems.className = "de-menu-items";
      tableMenu.items.forEach(function (item) {
        var el = button(item.label, item.label);
        el.className = "de-btn de-menu-item";
        el.addEventListener("click", function () {
          tmenu.removeAttribute("open");
          editor.chain().focus()[item.id]().run();
        });
        titems.appendChild(el);
      });
      tmenu.appendChild(titems);
      tmenu.addEventListener("toggle", function () {
        if (tmenu.open) openInRoom(tmenu, titems);
      });
      bar.appendChild(tmenu);
      var tableVisible = function () {
        var inTable = editor.isActive("table");
        tmenu.hidden = !inTable;
        if (!inTable) tmenu.removeAttribute("open");
      };
      editor.on("transaction", tableVisible);
      tableVisible();
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


  /* A menu opens where there is room (the review of #3110b37e, A2): on a
     short page the dropdown lands under the record bar, and some of her
     items can then not be pressed at all — measured, no scroll of the
     page clears her. On opening she measures her room herself: below to
     the window's edge and the record bar's top (where the screen carries
     one), above to the toolbar's. She opens downward when she fits, flips
     up when the room above is the larger, and caps herself with a scroll
     when neither holds — every item pressable on every page. */
  function openInRoom(menu, items) {
    items.style.maxHeight = "";
    menu.classList.remove("de-menu--up");
    var rect = items.getBoundingClientRect();
    var limit = window.innerHeight;
    var bar = document.querySelector("[data-action-bar]");
    if (bar) {
      var barTop = bar.getBoundingClientRect().top;
      if (barTop < limit) limit = barTop;
    }
    var below = limit - rect.top - 8;
    if (rect.height <= below) return;
    if (rect.top - rect.height - 12 >= 0) {
      menu.classList.add("de-menu--up");
      return;
    }
    items.style.maxHeight = Math.max(Math.round(below), 120) + "px";
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

  document.addEventListener("raak-button-chosen", function (event) {
    var editor = editors[event.detail.editor];
    if (!editor || editor.isDestroyed) return;
    /* All four destinations travel with the update, the chosen one set and
       the other three null (review A1 of 12 October 2026): an update that
       carried only the new one kept the old on the node, and the save
       refused the two of her with "precies één bestemming". */
    var attrs = {
      label: event.detail.label || "",
      variant: event.detail.variant || "secondary",
      page_id: null,
      href: null,
      form_slug: null,
      screen: null,
    };
    if (event.detail.kind === "page") attrs.page_id = event.detail.page_id;
    else if (event.detail.kind === "form") attrs.form_slug = event.detail.form_slug;
    else if (event.detail.kind === "screen") attrs.screen = "lid-worden";
    else attrs.href = event.detail.href || "";
    /* The change goes to the button AT THE POSITION the dialog opened for,
       not to whatever the selection is at apply time: between her click
       and Invoegen the dialog takes the focus, and a selection read at
       apply time saw the editor's own state where the update did not
       land (measured, review A1 of 12 October 2026). Nothing edits the
       document while the dialog is open, so the position cannot move. */
    var pos = event.detail.pos;
    if (pos !== null && pos !== undefined) {
      editor
        .chain()
        .focus()
        .command(function (props) {
          var node = props.state.doc.nodeAt(pos);
          if (node && node.type.name === "button") {
            props.dispatch(props.state.tr.setNodeMarkup(pos, null, attrs));
          }
          return true;
        })
        .run();
    } else {
      editor.chain().focus().insertContent({ type: "button", attrs: attrs }).run();
    }
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
    surface.className = "de-surface prose-raak";
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
    if ((config.insert || []).indexOf("columns") !== -1) {
      extensions = extensions.concat(columnsNode(RaakTiptap));
    }
    if ((config.insert || []).indexOf("button") !== -1) {
      extensions.push(buttonNode(RaakTiptap, config));
    }
    if ((config.insert || []).indexOf("callout") !== -1) {
      extensions.push(calloutNode(RaakTiptap));
    }

    var editor = new RaakTiptap.Editor({
      element: surface,
      extensions: extensions,
      content: input && input.value ? JSON.parse(input.value) : "",
    });

    /* Where the last click inside the editor landed — the menu's filter
       reads her when the selection is still the editor's untouched start
       (review S3 of 12 October 2026): the browser commits a clicked
       position to the editor's selection a moment after the click, and
       that moment is not deterministic; the click's own resolution is.
       She sits on the editor herself: the toolbar reads her from her own
       scope. */
    editor.laatsteKlik = null;

    /* A click on a button opens her own dialog, filled with what she holds
       (review A1 of 12 October 2026): the node is selected first, and the
       dialog carries her own position, so Invoegen changes her at that
       place instead of inserting a second one beside her. The walk up
       from the click asks every ancestor; a button at the top of the
       document is no one's child, so the node the cursor lands beside is
       asked too. */
    surface.addEventListener("click", function (event) {
      try {
        var pos = editor.view.posAtDOM(event.target, 0);
        editor.laatsteKlik = pos;
        var from = editor.state.doc.resolve(pos);
        for (var d = from.depth; d >= 1; d--) {
          var node = from.node(d);
          if (node.type.name === "button") {
            editor.chain().focus().setNodeSelection(from.before(d)).run();
            announce("raak-button-choose", {
              editor: mount.id,
              attrs: node.attrs,
              pos: from.before(d),
            });
            return;
          }
        }
        var erna = from.nodeAfter;
        if (erna && erna.type.name === "button") {
          editor.chain().focus().setNodeSelection(pos).run();
          announce("raak-button-choose", { editor: mount.id, attrs: erna.attrs, pos: pos });
          return;
        }
        var ervoor = from.nodeBefore;
        if (ervoor && ervoor.type.name === "button") {
          editor.chain().focus().setNodeSelection(pos - ervoor.nodeSize).run();
          announce("raak-button-choose", {
            editor: mount.id,
            attrs: ervoor.attrs,
            pos: pos - ervoor.nodeSize,
          });
        }
      } catch (error) {
        /* A click outside the text asks nothing. */
      }
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
