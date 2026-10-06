// CR-17 spike (#1626) — editor wiring under a strict CSP.
// The custom `value` node is the spike's own block: an inline atom with one
// attribute (`code`), in the toolbar and in the JSON document, exactly the
// shape C4.4 of change_request_17_web_content.md describes for value blocks.

(function () {
  "use strict";

  var bundle = window.RaakTiptap;

  var ValueNode = bundle.Node.create({
    name: "value",
    group: "inline",
    inline: true,
    atom: true,
    addAttributes: function () {
      return { code: { default: "LIDGELD" } };
    },
    renderHTML: function (args) {
      var node = args.node;
      var htmlAttributes = bundle.mergeAttributes(args.HTMLAttributes, {
        "data-value": node.attrs.code,
        class: "value-chip",
      });
      return ["span", htmlAttributes, "€ 35,00"];
    },
  });

  var editor = new bundle.Editor({
    element: document.getElementById("editor"),
    // StarterKit v3 includes link; TableKit is table + row + header + cell.
    extensions: [
      bundle.StarterKit,
      bundle.TableKit,
      bundle.Placeholder,
      ValueNode,
    ],
    content: "<p>Typ hier…</p>",
  });

  window.__spikeEditor = editor;

  var status = document.querySelector('[data-testid="status"]');
  function setStatus(text) {
    status.textContent = text;
  }

  function insertTable() {
    editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
  }

  var commands = {
    h1: function () { editor.chain().focus().toggleHeading({ level: 1 }).run(); },
    h2: function () { editor.chain().focus().toggleHeading({ level: 2 }).run(); },
    bold: function () { editor.chain().focus().toggleBold().run(); },
    italic: function () { editor.chain().focus().toggleItalic().run(); },
    table: insertTable,
    value: function () {
      editor.chain().focus().insertContent({ type: "value", attrs: { code: "LIDGELD" } }).run();
    },
    save: function () {
      var area = document.getElementById("saved-json");
      area.value = JSON.stringify(editor.getJSON());
      setStatus("Bewaard.");
    },
    load: function () {
      var area = document.getElementById("saved-json");
      if (!area.value.trim()) { setStatus("Niets te laden."); return; }
      editor.commands.setContent(JSON.parse(area.value));
      setStatus("Geladen.");
    },
    reset: function () {
      editor.commands.clearContent(true);
      setStatus("Leeg.");
    },
  };

  document.addEventListener("click", function (event) {
    var button = event.target.closest("button[data-command]");
    if (!button) return;
    commands[button.dataset.command]();
  });

  window.addEventListener("load", function () {
    // Marker for the load-time measurement: editor mounted and interactive.
    document.body.dataset.editorReady = String(performance.now());
    setStatus("Editor klaar.");
  });
})();
