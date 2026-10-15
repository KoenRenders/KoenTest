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

  /* The author's place when a dialog was opened, per editor: the document
     as it stood and her selection in it. Every dialog of the editor is
     opened through `announce`, so this is noted in one place; it is put
     back in one place too, when the dialog closes without having changed
     the document (the listener of `raak-editor-dialog-closed` below). */
  var opened = {};

  function announce(name, detail) {
    var editor = detail ? editors[detail.editor] : null;
    if (editor && !editor.isDestroyed) {
      opened[detail.editor] = { doc: editor.state.doc, place: editor.state.selection.getBookmark() };
    }
    /* bubbles: the dialogs listen on the window (Alpine's `.window`), and a
       CustomEvent without bubbles never leaves the document she was
       dispatched on — measured on the kit page: the link dialog stayed
       closed until she bubbles. */
    document.dispatchEvent(new CustomEvent(name, { detail: detail, bubbles: true }));
  }

  /* A dialog of the editor has closed (the shell `_editor_dialog` of the
     macro tells it, for every dialog and every way of closing). The dialog
     does not hand the focus back itself; the editor takes it here.
     - A choice changed the document: it is no longer equal to the one the
       dialog opened on. The answer to that choice has left the place at what
       it made; the editor only takes the focus.
     - The document is equal — no choice, or a choice that changed nothing (a
       link saved with the address it had, a card applied as it was): the
       editor takes the focus and the author's place is put back exactly —
       the selected block, the selected words, or the caret. Equal, not the
       same object: an unchanged choice makes a new document that is equal
       to the old one.
     Why the editor and not the dialog: handed back by the dialog's bare
     `focus()` on the editor's element, the browser's selection stood at the
     start of the page's first paragraph a few milliseconds later, and the
     editor followed it there (measured, 13 October 2026; see the macro). No
     script sets that selection, and what moves it is NOT identified — this
     is not an explanation, it is the place put back by the one who knows it. */
  document.addEventListener("raak-editor-dialog-closed", function (event) {
    var id = event.detail ? event.detail.editor : null;
    var editor = editors[id];
    var was = opened[id];
    delete opened[id];
    if (!editor || editor.isDestroyed) return;
    if (was && editor.state.doc.eq(was.doc)) {
      /* Only when the place is not there already: setting a selection clears
         the marks the author has just chosen for her next letters (a link
         made on a bare caret), also when it sets the selection she has. */
      var place = was.place.resolve(editor.state.doc);
      if (!editor.state.selection.eq(place)) editor.view.dispatch(editor.state.tr.setSelection(place));
    }
    /* At once, through the view — not the focus command, which waits for the
       next frame: the author's next key belongs to the editor (the kit's
       dialog handed the focus back at once too). The view writes the
       editor's selection into the page as it takes the focus. */
    editor.view.focus();
  });

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

  /* The section of CR-32 (F1–F3): a band of the page — blocks on a tone, with a
     small line above them. It stands at the document's root and nowhere else
     (the server's schema, F2a), so the document's own content expression is
     set here to `(block | section)+` and the section is in no group. The
     author chooses her tone (a name from the set, never a colour) and types
     her eyebrow in a bar above her blocks; the bar is the editor's, not the
     document's. */
  function sectionNode(RaakTiptap, config) {
    var words = config.section || { tones: [], toneLabel: "", eyebrowLabel: "" };
    var doc = RaakTiptap.Node.create({
      name: "doc",
      topNode: true,
      content: "(block | section)+",
    });
    var tones = words.tones.map(function (t) { return t.id; });
    function toneClass(tone) {
      return "prose-section" + (tone && tone !== "plain" ? " prose-section--" + tone : "");
    }
    var section = RaakTiptap.Node.create({
      name: "section",
      content: "block+",
      defining: true,
      isolating: true,
      addAttributes: function () {
        return { tone: { default: "plain" }, eyebrow: { default: null } };
      },
      parseHTML: function () {
        return [
          {
            tag: "div.prose-section",
            getAttrs: function (el) {
              var tone = tones.filter(function (t) { return el.classList.contains("prose-section--" + t); })[0];
              return { tone: tone || "plain" };
            },
          },
        ];
      },
      renderHTML: function (props) {
        return ["div", { class: toneClass(props.node.attrs.tone) }, 0];
      },
      addNodeView: function () {
        return function (props) {
          var node = props.node;
          var dom = document.createElement("div");
          dom.setAttribute("data-section", "");
          var bar = document.createElement("div");
          bar.className = "de-section-bar";
          bar.contentEditable = "false";
          var select = document.createElement("select");
          select.setAttribute("aria-label", words.toneLabel);
          select.className = "de-section-tone";
          words.tones.forEach(function (t) {
            var option = document.createElement("option");
            option.value = t.id;
            option.textContent = t.label;
            select.appendChild(option);
          });
          var eyebrow = document.createElement("input");
          eyebrow.type = "text";
          eyebrow.maxLength = 80;
          eyebrow.className = "de-section-eyebrow";
          eyebrow.placeholder = words.eyebrowLabel;
          eyebrow.setAttribute("aria-label", words.eyebrowLabel);
          bar.appendChild(select);
          bar.appendChild(eyebrow);
          var content = document.createElement("div");
          content.className = "de-section-content";
          dom.appendChild(bar);
          dom.appendChild(content);
          function paint() {
            dom.className = toneClass(node.attrs.tone);
            select.value = node.attrs.tone;
            if (document.activeElement !== eyebrow) eyebrow.value = node.attrs.eyebrow || "";
          }
          function set(change) {
            var pos = props.getPos();
            if (typeof pos !== "number") return;
            var attrs = Object.assign({}, node.attrs, change);
            props.editor.view.dispatch(props.editor.state.tr.setNodeMarkup(pos, undefined, attrs));
          }
          select.addEventListener("change", function () { set({ tone: select.value }); });
          eyebrow.addEventListener("input", function () { set({ eyebrow: eyebrow.value.trim() ? eyebrow.value : null }); });
          paint();
          return {
            dom: dom,
            contentDOM: content,
            update: function (updated) {
              if (updated.type.name !== "section") return false;
              node = updated;
              paint();
              return true;
            },
            stopEvent: function (event) { return bar.contains(event.target); },
            ignoreMutation: function (mutation) { return bar.contains(mutation.target); },
          };
        };
      },
    });
    return [doc, section];
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

  /* The cards of CR-17 (C4.9): a block that holds cards and nothing else,
     and a card that is an atom — the author fills her in the dialog of the
     macro, never by typing. What a card holds is her attributes: the title,
     the line, an icon of the kit or a picture, the labels, and the ONE
     destination (the button's four). The card draws herself the way the site
     draws her, so the author sees the row she is making; her icon is taken
     from the dialog's own choice of icons, the one place the page carries the
     kit's drawings. */
  var CARD_ATTRS = ["title", "line", "icon", "media_id", "labels", "page_id", "href", "form_slug", "screen"];

  function cardView(node, mediaUrl, mountId) {
    var a = node.attrs;
    var dom = document.createElement("div");
    dom.className = "prose-card";
    dom.setAttribute("data-card", "");
    if (a.media_id) {
      var img = document.createElement("img");
      img.className = "prose-card-picture";
      img.src = mediaUrl + a.media_id;
      img.alt = "";
      dom.appendChild(img);
    } else if (a.icon) {
      var tile = document.createElement("span");
      tile.className = "prose-card-icon";
      var source = document.querySelector(
        '[data-card-dialog="' + mountId + '"] [data-card-icon="' + a.icon + '"] svg'
      );
      if (source) {
        var svg = source.cloneNode(true);
        svg.setAttribute("width", "24");
        svg.setAttribute("height", "24");
        tile.appendChild(svg);
      }
      dom.appendChild(tile);
    }
    var title = document.createElement("span");
    title.className = "prose-card-title";
    title.textContent = a.title || "";
    dom.appendChild(title);
    if (a.line) {
      var line = document.createElement("span");
      line.className = "prose-card-line";
      line.textContent = a.line;
      dom.appendChild(line);
    }
    if (a.labels && a.labels.length) {
      var labels = document.createElement("span");
      labels.className = "prose-card-labels";
      labels.textContent = a.labels.join(" · ");
      dom.appendChild(labels);
    }
    return dom;
  }

  function cardsNodes(RaakTiptap, config, mountId) {
    var mediaUrl = (config.figure && config.figure.mediaUrl) || "";
    var cards = RaakTiptap.Node.create({
      name: "cards",
      group: "block",
      content: "card+",
      parseHTML: function () {
        return [{ tag: "div[data-cards]" }];
      },
      /* The block's element is NOT editable in the editor's page. A card is
         an atom, and the editor marks each atom's element non-editable; the
         block then held nothing but non-editable elements inside an editable
         one. A selected card that is neither the first nor the last has both
         ends of the browser's selection between two such elements, and at
         the author's next key — any key, Shift alone — the browser put its
         selection at the start of the page's first paragraph and the editor
         followed it (measured, 13 October 2026: inner cards 30 of 30, the
         first and the last never). With the block itself non-editable the
         browser leaves the selection where the editor put it. WHEN the
         browser moves it is measured; WHY it does is not known. Nothing in
         the block is typed in: the author fills a card in her dialog.

         Why this attribute stays beside `holdWholeBlock` below, which keeps
         every other whole block selected by drawing an element after it:
         inside this block that element would be a child of the block, and
         the block's columns count its children — two cards and the element
         read as three, and the two cards went from 384 to 251 px wide while
         one was selected (measured, 13 October 2026). An element before the
         block instead did not keep an inner card. So a CONTAINER of whole
         blocks keeps their selection by being non-editable itself; a later
         container like this one needs the same attribute. The one case the
         attribute does not cover is a card that is alone in the block:
         `holdWholeBlock` draws its element there, and only there. */
      renderHTML: function () {
        return ["div", { "data-cards": "", class: "prose-cards", contenteditable: "false" }, 0];
      },
    });
    var card = RaakTiptap.Node.create({
      name: "card",
      atom: true,
      addAttributes: function () {
        var attrs = {};
        CARD_ATTRS.forEach(function (name) {
          attrs[name] = { default: name === "title" ? "" : null };
        });
        return attrs;
      },
      /* Copy and paste inside the editor: the attributes travel as one
         JSON attribute and come back as they left. */
      parseHTML: function () {
        return [
          {
            tag: "div[data-card]",
            getAttrs: function (el) {
              try {
                return JSON.parse(el.getAttribute("data-card") || "{}");
              } catch (error) {
                return false;
              }
            },
          },
        ];
      },
      renderHTML: function (props) {
        return ["div", { "data-card": JSON.stringify(props.node.attrs), class: "prose-card" }, props.node.attrs.title || ""];
      },
      addNodeView: function () {
        return function (props) {
          return { dom: cardView(props.node, mediaUrl, mountId) };
        };
      },
    });
    return [cards, card];
  }

  /* A block selected as a whole keeps its selection (CR-17).

     Measured on 13 October 2026: a picture or a button selected as a whole
     lost its selection at the author's next key — any key, Shift alone — when
     the blocks on BOTH its sides were non-editable ones (a picture between
     two buttons, the middle one of three pictures, a picture between a
     button and a cards block: 3 of 3 each; kept where a paragraph or a
     Kader stood on one side). Some milliseconds after the keydown the
     browser's selection stood at the start of the page's first paragraph
     and the editor followed it, so Delete took a letter at the top of the
     page. No script moves that selection. WHEN the browser does is
     measured; WHY is not known.

     What keeps it, measured before this was written: one element of the
     editor's own right after the selected block — non-editable and empty,
     so it takes no room in the page — as the gap cursor draws one for its own
     position. An editable element did not
     help; an element before the block moved the block where the site's
     rule "the first block of a column has no top margin" stopped applying.

     One rule for every block the editor selects as a whole that stands in
     the page or in a column — a block added later has it without knowing.
     Inside a CONTAINER of such blocks (the cards block), three things, in
     this order, each measured on 13 October 2026:
     1. A block with a sibling there is kept by the container's own
        non-editable attribute (see the cards block): the first and the
        second of two cards, the middle one of three — kept 3 of 3 each,
        with no element.
     2. A block that is ALONE in its container is not: the only card of a
        block lost its selection at the next key, 5 of 5 — and under load
        in the middle of the test that removes cards one by one, 18 of 40
        times at the removal that leaves one. It gets the element, inside
        the container, after itself: kept 3 of 3. An element after or
        before the container did not keep it (lost 3 of 3 each).
     3. With one child the element moves nothing (every element's box the
        same before and while) — once the editor's stylesheet takes it out
        of the block's rows and leaves it a height: as a row of its own, on
        a phone, the block grew 16 px and the card was not kept; out of the
        rows without a height it was not kept at either width. With more
        than one child it would move things whatever its style: two cards
        went from 384 to 251 px wide (the block's columns count its
        children) — which is why it is not drawn there, and need not be. */
  function holdWholeBlock(RaakTiptap) {
    return RaakTiptap.Extension.create({
      name: "holdWholeBlock",
      addProseMirrorPlugins: function () {
        return [
          new RaakTiptap.Plugin({
            key: new RaakTiptap.PluginKey("holdWholeBlock"),
            props: {
              decorations: function (state) {
                var selection = state.selection;
                if (!selection.node) return null;
                /* Inside a container of whole blocks — a parent that
                   cannot hold a paragraph, as the cards block — only for
                   a block that is ALONE there. Asked of the document (the
                   schema, the number of children), not of a list of names. */
                var parent = selection.$from.parent;
                var container = !parent.type.contentMatch.matchType(state.schema.nodes.paragraph);
                if (container && parent.childCount > 1) return null;
                var hold = function () {
                  var element = document.createElement("span");
                  element.className = "de-hold";
                  element.setAttribute("contenteditable", "false");
                  return element;
                };
                return RaakTiptap.DecorationSet.create(state.doc, [
                  RaakTiptap.Decoration.widget(selection.to, hold, { side: 1, key: "de-hold" }),
                ]);
              },
            },
          }),
        ];
      },
    });
  }

  /* The card the selection stands on, with her place — or null. A card is an
     atom, so a click or the arrow keys select her as a node. */
  function selectedCard(editor) {
    var selection = editor.state.selection;
    if (selection.node && selection.node.type.name === "card") {
      return { node: selection.node, pos: selection.from };
    }
    return null;
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

  /* A placed picture's own dialog, with what the picture holds. The
     picture is the selection — the click selected it, the menu's item saw
     it selected — so Invoegen replaces THAT picture (see
     `raak-figure-chosen`). Called for a click on
     the picture and for the insert menu's item with a picture selected. */
  function announceFigure(editor, editorId, config, pos) {
    var node = editor.state.doc.nodeAt(pos);
    if (!node || node.type.name !== "figure") return;
    announce("raak-figure-choose", {
      editor: editorId,
      attrs: node.attrs,
      url: ((config.figure && config.figure.mediaUrl) || "") + node.attrs.media_id,
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

    /* A block the toolbar turns on and off, as a list (#1985): the
       quotation. Its word is the configuration's, like every word here. */
    (config.toolbar.blocks || []).forEach(function (block) {
      if (block.id !== "blockquote") return;
      var el = button(block.label);
      el.addEventListener("click", function () {
        editor.chain().focus().toggleBlockquote().run();
      });
      press.push({
        el: el,
        isOn: function () {
          return editor.isActive("blockquote");
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
        item.id === "callout" ||
        item.id === "cards" ||
        item.id === "section"
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
          } else if (item.id === "section") {
            /* The blocks she has selected become the section; where that is
               not possible (inside a column, a cell, another section) a new
               one is put at the document's end — a section stands at the
               root only. */
            if (!editor.chain().focus().wrapIn("section", { tone: "plain" }).run()) {
              editor.chain().focus().insertContentAt(editor.state.doc.content.size, {
                type: "section",
                attrs: { tone: "plain" },
                content: [{ type: "paragraph" }],
              }).run();
            }
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
          } else if (item.id === "cards") {
            /* A card never lands without her title and her destination:
               the dialog first, the block with that one card after. */
            announce("raak-card-choose", { editor: editorId, attrs: null, pos: null, mode: "new" });
          } else if (config.figure) {
            /* The figure never lands without her picture: the dialog of
               the macro opens the kit's picker, and the server's shape
               gate refuses a document that saves such a figure anyway.
               With a picture selected the dialog opens with what that
               picture holds and Invoegen changes it at its own place — as
               for the button above; without, it opened empty and put a
               second picture beside the first (the comparison with the
               Trix editor, 14 October 2026). */
            var chosenFigure = editor.state.selection.node;
            if (chosenFigure && chosenFigure.type.name === "figure") {
              announceFigure(editor, editorId, config, editor.state.selection.from);
            } else {
              announce("raak-figure-choose", { editor: editorId });
            }
          }
        });
        items.appendChild(el);
      });
      /* The codes (CR-17): one item that opens the macro's list. The
         screen decides whether there is one — the mount carries the item's
         word when the caller passed codes — and the list itself stands in
         the macro, from the caller's own list: none is written here. */
      var codesMount = document.getElementById(editorId);
      if (codesMount && codesMount.dataset.codesLabel) {
        var codeItem = button(codesMount.dataset.codesLabel, codesMount.dataset.codesLabel);
        codeItem.className = "de-btn de-menu-item";
        codeItem.setAttribute("data-insert-code", "");
        codeItem.addEventListener("click", function () {
          menu.removeAttribute("open");
          announce("raak-code-choose", { editor: editorId });
        });
        items.appendChild(codeItem);
      }
      menu.appendChild(items);
      menu.addEventListener("toggle", function () {
        if (menu.open) {
          /* "Kolommen" is not offered inside a column (review S3 of 12
             October 2026): the editor would insert the nested block and
             the save would refuse her — the menu offers what the save
             takes. The SELECTION is asked, alone (review F1 of 12
             October 2026): the browser commits a clicked position to the
             editor's selection a moment after the click, but the menu
             opens on a second click — the summary — and by then the
             selection stands where the author clicked, also after the
             arrows and after typing. The click's own position, first
             read here, stayed standing after the author walked away from
             it and hid "Kolommen" where she was going. The ancestors are
             asked by hand (`isActive` answers the selection's own node).
             The display goes on the style and not on the `hidden`
             attribute: the editor's own css sets `display` on `.de-btn`,
             and an attribute loses from her. */
          if (kolommen_el) {
            var inKolom = false;
            var hier = editor.state.selection.$from;
            for (var d = hier.depth; d >= 1; d--) {
              if (hier.node(d).type.name === "column") {
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

    /* The cards menu (CR-17, C4.9): what the author does to the card she
       stands on — another card after her, one place forward or back, away.
       Hidden until a card is selected, like the table menu outside a table.
       The first card cannot go forward and the last not back; the item says
       so by being off. */
    var cardsMenu = config.toolbar.cardsMenu;
    if (cardsMenu) {
      var cmenu = document.createElement("details");
      cmenu.className = "de-menu de-menu-cards";
      cmenu.hidden = true;
      var csummary = document.createElement("summary");
      csummary.className = "de-btn de-menu-toggle";
      csummary.textContent = cardsMenu.label + " ▾";
      /* The card the menu was opened for. The press on the menu's own
         summary moves the browser's selection, and the editor follows it off
         the card (measured: 14 ms after the menu opened the card was no
         longer selected and the menu hid itself under the pointer). So the
         card is read at the press, before anything moves, and every item
         works on that one. */
      var held = null;
      var heldCard = function () {
        if (!held) return null;
        var node = editor.state.doc.nodeAt(held.pos);
        return node && node.type.name === "card" ? { node: node, pos: held.pos } : null;
      };
      csummary.addEventListener("mousedown", function (event) {
        event.preventDefault();
        if (!cmenu.open) held = selectedCard(editor);
      });
      csummary.addEventListener("keydown", function (event) {
        if ((event.key === "Enter" || event.key === " ") && !cmenu.open) held = selectedCard(editor);
      });
      cmenu.appendChild(csummary);
      var citems = document.createElement("div");
      citems.className = "de-menu-items";
      var cardButtons = {};
      var moveCard = function (step) {
        var here = heldCard();
        if (!here) return;
        var at = editor.state.doc.resolve(here.pos);
        var index = at.index();
        var block = at.parent;
        if (index + step < 0 || index + step >= block.childCount) return;
        var other = block.child(index + step);
        var target = step < 0 ? here.pos - other.nodeSize : here.pos + other.nodeSize;
        editor
          .chain()
          .focus()
          .command(function (props) {
            props.tr.delete(here.pos, here.pos + here.node.nodeSize).insert(target, here.node);
            return true;
          })
          .setNodeSelection(target)
          .run();
      };
      cardsMenu.items.forEach(function (item) {
        var el = button(item.label, item.label);
        el.className = "de-btn de-menu-item";
        el.setAttribute("data-card-action", item.id);
        cardButtons[item.id] = el;
        el.addEventListener("click", function () {
          cmenu.removeAttribute("open");
          var here = heldCard();
          if (!here) return;
          if (item.id === "edit") {
            announce("raak-card-choose", { editor: editorId, attrs: here.node.attrs, pos: here.pos, mode: "edit" });
          } else if (item.id === "add") {
            announce("raak-card-choose", { editor: editorId, attrs: null, pos: here.pos, mode: "after" });
          } else if (item.id === "forward") {
            moveCard(-1);
          } else if (item.id === "back") {
            moveCard(1);
          } else if (item.id === "remove") {
            var at = editor.state.doc.resolve(here.pos);
            /* The last card takes her block along: a block without a card
               is one the save refuses. */
            var from = at.parent.childCount === 1 ? at.before() : here.pos;
            var to = at.parent.childCount === 1 ? at.after() : here.pos + here.node.nodeSize;
            editor.chain().focus().deleteRange({ from: from, to: to }).run();
          }
        });
        citems.appendChild(el);
      });
      cmenu.appendChild(citems);
      var cardsVisible = function () {
        /* An open menu stays: it works on the card it holds. */
        var here = cmenu.open ? heldCard() : selectedCard(editor);
        cmenu.hidden = !here;
        if (!here) {
          cmenu.removeAttribute("open");
          return;
        }
        var at = editor.state.doc.resolve(here.pos);
        if (cardButtons.forward) cardButtons.forward.disabled = at.index() === 0;
        if (cardButtons.back) cardButtons.back.disabled = at.index() === at.parent.childCount - 1;
      };
      cmenu.addEventListener("toggle", function () {
        if (cmenu.open) openInRoom(cmenu, citems);
        else held = null;
        cardsVisible();
      });
      bar.appendChild(cmenu);
      editor.on("transaction", cardsVisible);
      cardsVisible();
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
    /* Where the author was writing — or, when the dialog was opened on a
       placed picture, over that picture: it is the selection, and an insert
       over a selected block replaces it. */
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

  document.addEventListener("raak-card-chosen", function (event) {
    var editor = editors[event.detail.editor];
    if (!editor || editor.isDestroyed) return;
    var choice = event.detail;
    /* Every attribute travels, the chosen ones set and the others null —
       the button's lesson (review A1 of 12 October 2026): an update that
       carried only the new destination kept the old one on the node. */
    var attrs = {
      title: choice.title || "",
      line: choice.line || null,
      icon: choice.top === "icon" ? choice.icon || null : null,
      media_id: choice.top === "picture" ? choice.media_id || null : null,
      labels: choice.labels && choice.labels.length ? choice.labels : null,
      page_id: null,
      href: null,
      form_slug: null,
      screen: null,
    };
    if (choice.kind === "page") attrs.page_id = choice.page_id;
    else if (choice.kind === "form") attrs.form_slug = choice.form_slug;
    else if (choice.kind === "screen") attrs.screen = "lid-worden";
    else attrs.href = choice.href || "";
    var pos = choice.pos;
    if (choice.mode === "new" || pos === null || pos === undefined) {
      editor
        .chain()
        .focus()
        .insertContent({ type: "cards", content: [{ type: "card", attrs: attrs }] })
        .run();
      return;
    }
    /* At the position the dialog opened for, not at the selection of the
       moment — the dialog holds the focus in between. */
    editor
      .chain()
      .focus()
      .command(function (props) {
        var node = props.state.doc.nodeAt(pos);
        if (!node || node.type.name !== "card") return true;
        if (choice.mode === "after") {
          props.tr.insert(pos + node.nodeSize, node.type.create(attrs));
        } else {
          props.tr.setNodeMarkup(pos, null, attrs);
        }
        return true;
      })
      .setNodeSelection(choice.mode === "after" ? pos + 1 : pos)
      .run();
  });

  /* An outside address as the button's and the card's dialog check it —
     the server's own rule (http(s), no white space), asked before anything
     travels to the editor. Returns "" when it is one, else which half it
     broke: "start" or "space". One function, so the two dialogs and the
     schema cannot each grow a rule of their own. */
  window.raakOutsideAddress = function (address) {
    var ok =
      (address.indexOf("http://") === 0 && address.length > 7) ||
      (address.indexOf("https://") === 0 && address.length > 8);
    if (!ok) return "start";
    return /\s/.test(address) ? "space" : "";
  };

  /* A code is text: it lands at the cursor as the characters an author
     would type, and nothing in the document says it was chosen. */
  document.addEventListener("raak-code-chosen", function (event) {
    var editor = editors[event.detail.editor];
    if (!editor || editor.isDestroyed || !event.detail.code) return;
    editor.chain().focus().insertContent({ type: "text", text: event.detail.code }).run();
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
    var RaakTiptap = window.RaakTiptap;
    /* Ready only once the library is there: a build without her would
       mark the mount ready and close the door for good — the scan below
       returns on her own arrival (review M1 of 12 October 2026). */
    if (!RaakTiptap) return;
    mount.dataset.ready = "1";
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

    var starterOptions = {
        heading: { levels: config.headings.map(function (h) { return h.level; }) },
        strike: (config.marks || []).indexOf("strike") !== -1,
        link: (config.marks || []).indexOf("link") !== -1,
        bulletList: (config.lists || []).indexOf("bulletList") !== -1,
        orderedList: (config.lists || []).indexOf("orderedList") !== -1,
        /* The quotation is on where the set offers it (#1985): the kit's
           own block, with her "> " at the start of a paragraph and a pasted
           <blockquote> kept as one. */
        blockquote: (config.blocks || []).indexOf("blockquote") !== -1,
        /* Off, so the editor cannot write what the server refuses (review
           B1, #1699): no set has code, a code block, a rule or underline — a
           typed or pasted one would become a document the schema refuses
           with "Onbekend blok". They come back when a set offers them. */
        code: false,
        codeBlock: false,
        horizontalRule: false,
        underline: false,
    };
    /* A set with the section brings her own document node (`sectionNode`):
       the starter kit's would refuse her at the root. */
    var withSection = (config.insert || []).indexOf("section") !== -1;
    if (withSection) starterOptions.document = false;
    var extensions = [holdWholeBlock(RaakTiptap), RaakTiptap.StarterKit.configure(starterOptions)];
    if (withSection) {
      extensions = extensions.concat(sectionNode(RaakTiptap, config));
    }
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
    if ((config.insert || []).indexOf("cards") !== -1) {
      extensions = extensions.concat(cardsNodes(RaakTiptap, config, mount.id));
    }

    var editor = new RaakTiptap.Editor({
      element: surface,
      extensions: extensions,
      content: input && input.value ? JSON.parse(input.value) : "",
    });

    /* A click on a button opens her own dialog, filled with what she holds
       (review A1 of 12 October 2026): the node is selected first, and the
       dialog carries her own position, so Invoegen changes her at that
       place instead of inserting a second one beside her. Only the button
       herself opens it (review F2 of 12 October 2026): a click on the
       editor's own element resolves to position 0, and asking "the node
       beside it" opened the document's first button from the empty room
       under the text — an author who clicks there to go on writing got a
       dialog. The click's target (or her ancestor) must be the button. */
    surface.addEventListener("click", function (event) {
      var knop = event.target.closest ? event.target.closest("a[data-button]") : null;
      if (!knop) return;
      try {
        var pos = editor.view.posAtDOM(knop, 0);
        var from = editor.state.doc.resolve(pos);
        var node = from.nodeAfter || from.nodeBefore;
        if (node && node.type.name === "button") {
          var knopPos = node === from.nodeAfter ? pos : pos - node.nodeSize;
          editor.chain().focus().setNodeSelection(knopPos).run();
          announce("raak-button-choose", {
            editor: mount.id,
            attrs: node.attrs,
            pos: knopPos,
          });
        }
      } catch (error) {
        /* A click outside the text asks nothing. */
      }
    });
    /* A click on a placed picture opens its dialog with what it holds, as
       a click on a button does: the Trix editor offered "Bewerken" on a
       picture (#1224), and here a click offered nothing — to correct a
       typing fault in the alternative text an author had to remove the
       picture and place it again. The click's target must be the picture. */
    surface.addEventListener("click", function (event) {
      var figure = event.target.closest ? event.target.closest("figure[data-document-figure]") : null;
      if (!figure || !surface.contains(figure)) return;
      try {
        var at = editor.view.posAtDOM(figure, 0);
        var here = editor.state.doc.resolve(at);
        var found = here.nodeAfter && here.nodeAfter.type.name === "figure" ? at : at - 1;
        announceFigure(editor, mount.id, config, found);
      } catch (error) {
        /* A click outside the text asks nothing. */
      }
    });
    /* A click on a card selects her and opens her dialog with what she
       holds; Enter on a selected card does the same for the keyboard. The
       click's target must be the card herself, as for the button. */
    var openCard = function (cardPos) {
      var node = editor.state.doc.nodeAt(cardPos);
      if (!node || node.type.name !== "card") return;
      editor.chain().focus().setNodeSelection(cardPos).run();
      announce("raak-card-choose", { editor: mount.id, attrs: node.attrs, pos: cardPos, mode: "edit" });
    };
    surface.addEventListener("click", function (event) {
      var kaart = event.target.closest ? event.target.closest("[data-card]") : null;
      if (!kaart) return;
      try {
        openCard(editor.view.posAtDOM(kaart, 0));
      } catch (error) {
        /* A click outside the text asks nothing. */
      }
    });
    surface.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      var here = selectedCard(editor);
      if (!here) return;
      event.preventDefault();
      event.stopPropagation();
      openCard(here.pos);
    }, true);
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

  /* The library can still be on her way: a swapped fragment brings both
     scripts as her own requests, and they run in the network's order,
     not the tags' (review M1 of 12 October 2026). Every script in the
     document that has not run yet gets a listener; the one that brings
     the library wakes the scan. A script that already ran never fires
     her `load` again — harmless: then the library is there and the scan
     below builds at once. */
  var watchedScripts = [];
  function watchScripts() {
    document.querySelectorAll("script").forEach(function (script) {
      if (watchedScripts.indexOf(script) < 0) {
        watchedScripts.push(script);
        script.addEventListener("load", scan);
      }
    });
  }

  function scan() {
    if (!window.RaakTiptap) watchScripts();
    document.querySelectorAll("[data-document-editor]").forEach(build);
  }
  /* Build what stands on the page when this script runs, not only at a
     later event: a page reached through a boosted link brings this
     script inside the swapped fragment, and the swap that carried her
     is past when she runs — what builds the editor today is a later
     swap of something else, with some 35 ms to spare (review M1 of 12
     October 2026). */
  scan();
  document.addEventListener("DOMContentLoaded", scan);
  document.addEventListener("htmx:afterSwap", scan);
})();
