"""Design Studio (CR-10, #1007): posters and social images made from an activity.

A *design* belongs to an activity and stores its inputs — template, colour
pair, design text, images with their focal points — never its renders. The
renders are made by merging those inputs into an SVG template and handing the
SVG to Inkscape (PDF, PNG). The merged SVG is also the editable file a unit can
download, rework in Inkscape and upload again.

Layout of the package:

- ``brand``     — the Raak house style as data: eight colours, twelve permitted
                  duos, the three enabled today, and the gate that checks a
                  template against them.
- ``richtext``  — the formatted-text subset (paragraphs, bold, bullets) and its
                  rendering to SVG text spans, with line wrapping on real font
                  metrics.
- ``models``    — schema ``designstudio``. (Uploaded SVGs are cleaned by
                  ``media``'s one allowlist, #1011 — no cleaner lives here.)
- ``render``    — merge, overflow check (estimate + Inkscape as authority),
                  Inkscape export.
- ``service``   — designs, versions, publishing, staleness.
- ``api``       — the facade other components may import.
"""
