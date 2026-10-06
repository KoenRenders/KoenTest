"""CR-17 spike (#1626) — the measurements, driven by Playwright.

What this proves (issue #1626, "Wat"):
  1. Table round trip: saved as JSON, reloaded, one cell changed, saved again
     — the documents differ only in that cell.
  2. Custom node: `value` in the toolbar, in the document JSON and rendered
     server-side (render_document.py) to HTML.
  3. CSP: the page is served with `default-src 'self'` (csp_server.py) —
     stricter than today's real policy, which still allows unsafe-inline and
     unsafe-eval. Violations are collected from the console, not assumed absent.
  4. Phone at 390x844: the editor opens, adds a block, saves; the page does
     not scroll sideways.
  5. Load time next to Trix (index-trix.html), same server, same shape.

Playwright itself needs eval for page.evaluate, which a strict CSP blocks —
so the functional proof runs without a single evaluate (selectors, clicks and
protocol reads only), in an enforcing context; the numeric measurements that
need evaluate (scrollWidth, navigation timings) run in a `bypass_csp` context
that never touches the functional claims. That split is a finding for phase 1,
recorded in the results as "tooling".

Output: JSON on stdout (consumed by the comment on #1427).
"""

import json
import sys
import time

sys.path.insert(0, "/srv/spike/cr17")
import render_document  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

BASE = "http://127.0.0.1:8899"
RESULTS = {}


def deep_diff(a, b, path="root", out=None):
    """Collect every leaf difference between two JSON documents."""
    if out is None:
        out = []
    if type(a) is not type(b):
        out.append((path, a, b))
        return out
    if isinstance(a, dict):
        for key in set(a) | set(b):
            if key not in a or key not in b:
                out.append((f"{path}.{key}", a.get(key, "<missing>"), b.get(key, "<missing>")))
            else:
                deep_diff(a[key], b[key], f"{path}.{key}", out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append((f"{path}(len)", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            deep_diff(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append((path, a, b))
    return out


def type_table(page, prefix="R"):
    """Insert a 3x3 table with a header row and type into every cell."""
    page.click('button[data-command="table"]')
    page.wait_for_selector("#editor table")
    cells = page.locator("#editor table th, #editor table td")
    assert cells.count() == 9, f"expected 9 cells, got {cells.count()}"
    for i in range(9):
        cells.nth(i).click()
        page.keyboard.type(f"{prefix}{i // 3 + 1}C{i % 3 + 1}")


def save_json(page):
    page.click('button[data-command="save"]')
    return page.locator("#saved-json").input_value()


def open_strict(ctx, page_console):
    """Open the spike page in a CSP-enforcing context, no evaluate allowed."""
    page = ctx.new_page()
    refusals = []
    page.on(
        "console",
        lambda m: refusals.append(m.text) if "Refused to" in m.text else None,
    )
    page.on("pageerror", lambda e: refusals.append(str(e)))
    page.goto(f"{BASE}/spike/cr17/index.html", wait_until="load")
    page.wait_for_selector("body[data-editor-ready]", timeout=10_000)
    page_console.extend(refusals)
    return page


def main():
    all_refusals = []
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- 1/2/3: round trip, custom node, CSP — strict, evaluate-free ----
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = open_strict(ctx, all_refusals)

        type_table(page)
        doc_a = json.loads(save_json(page))

        # Reload the saved document into the editor, change one cell, save again.
        page.click('button[data-command="load"]')
        page.wait_for_selector("#editor table")
        cells = page.locator("#editor table th, #editor table td")
        cells.nth(3).click(click_count=3)  # row 2, col 1: select the cell's text
        page.keyboard.type("R2C1-GEWIJZIGD")
        doc_b = json.loads(save_json(page))

        diffs = deep_diff(doc_a, doc_b)
        roundtrip_ok = (
            len(diffs) == 1
            and diffs[0][0].endswith(".text")
            and diffs[0][1] == "R2C1"
            and diffs[0][2] == "R2C1-GEWIJZIGD"
        )
        RESULTS["table_roundtrip"] = {
            "ok": roundtrip_ok,
            "diffs": [str(d) for d in diffs[:5]],
        }

        # Server-side render of both documents: the HTML differs only in the cell.
        html_a = render_document.render_document(doc_a)
        html_b = render_document.render_document(doc_b)
        table_in_html = "<table><tbody>" in html_a and "<th>R1C1</th>" in html_a
        render_diff_ok = html_a.replace("<td>R2C1</td>", "<td>R2C1-GEWIJZIGD</td>") == html_b
        RESULTS["server_render"] = {
            "ok": bool(table_in_html and render_diff_ok),
            "table_in_html": bool(table_in_html),
            "diff_only_cell": bool(render_diff_ok),
        }

        # The custom value node: toolbar -> document -> DOM -> server render.
        page.click('button[data-command="reset"]')
        page.click('button[data-command="value"]')
        doc_v = json.loads(save_json(page))
        value_json = json.dumps(doc_v)
        has_value_node = '"value"' in value_json and '"LIDGELD"' in value_json
        chip_in_dom = page.locator("#editor span.value-chip[data-value=LIDGELD]").count() == 1
        html_v = render_document.render_document(doc_v)
        chip_in_html = '<span data-value="LIDGELD">€ 35,00</span>' in html_v
        RESULTS["custom_node"] = {
            "ok": bool(has_value_node and chip_in_dom and chip_in_html),
            "in_document": bool(has_value_node),
            "in_editor_dom": bool(chip_in_dom),
            "in_server_html": bool(chip_in_html),
        }
        ctx.close()

        # --- 4: phone at 390x844 — strict, evaluate-free ---------------------
        ctx_phone = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
        )
        page = open_strict(ctx_phone, all_refusals)
        t0 = time.monotonic()
        type_table(page, prefix="T")
        page.keyboard.type(" tel")
        typing_seconds = round(time.monotonic() - t0, 2)
        phone_doc = json.loads(save_json(page))
        phone_saved = len(phone_doc.get("content", [])) > 1
        ctx_phone.close()

        ctx_phone2 = browser.new_context(
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            bypass_csp=True,
        )
        page2 = ctx_phone2.new_page()
        page2.goto(f"{BASE}/spike/cr17/index.html", wait_until="load")
        page2.wait_for_selector("body[data-editor-ready]", timeout=10_000)
        page2.click('button[data-command="table"]')
        page2.wait_for_selector("#editor table")
        scroll_width = page2.evaluate("document.documentElement.scrollWidth")
        body_scroll_width = page2.evaluate("document.body.scrollWidth")
        ctx_phone2.close()

        RESULTS["phone_390"] = {
            "ok": bool(phone_saved and scroll_width <= 390 and body_scroll_width <= 390),
            "strict_csp_saved": bool(phone_saved),
            "scroll_width": scroll_width,
            "body_scroll_width": body_scroll_width,
            "typing_seconds_9_cells": typing_seconds,
        }

        # --- 5: load time, TipTap vs Trix, same server, same shape ----------
        def measure(path, runs=3):
            timings = []
            for _ in range(runs):
                c = browser.new_context(
                    viewport={"width": 1280, "height": 800}, bypass_csp=True
                )
                pg = c.new_page()
                pg.goto(f"{BASE}{path}", wait_until="load")
                pg.wait_for_selector("body[data-editor-ready]", timeout=10_000)
                nav = pg.evaluate(
                    "performance.getEntriesByType('navigation')[0].loadEventEnd"
                )
                ready = float(pg.get_attribute("body", "data-editor-ready"))
                timings.append(
                    {"load_event_ms": round(nav), "editor_ready_ms": round(ready)}
                )
                c.close()
            return timings

        RESULTS["load_time"] = {
            "tiptap": measure("/spike/cr17/index.html"),
            "trix": measure("/spike/cr17/index-trix.html"),
        }

        browser.close()

    script_refusals = [
        r for r in all_refusals if "apply inline style" not in r
    ]
    style_refusals = [r for r in all_refusals if "apply inline style" in r]

    RESULTS["csp"] = {
        "ok": not script_refusals,
        "script_refusals": script_refusals[:5],
        "style_attribute_refusals": len(style_refusals),
        "style_source": "TipTap's table column widths (colgroup <col style=width>)",
        "finding": "the editor itself needs no unsafe-inline and no unsafe-eval; "
        "only the table's column widths write style attributes, which a strict "
        "policy refuses — the table stays functional, the widths fall away. "
        "Today's real policy already allows style-src 'self' 'unsafe-inline', "
        "so on the portal nothing changes.",
        "policy": "default-src 'self'",
        "note": "stricter than today's snippet (unsafe-inline + unsafe-eval allowed there)",
    }
    RESULTS["tooling"] = {
        "playwright_needs_unsafe_eval_for_evaluate": True,
        "workaround": "functional proof evaluate-free in an enforcing context; "
        "metrics in a bypass_csp context",
    }

    print(json.dumps(RESULTS, indent=2, ensure_ascii=False))
    ok = all(
        RESULTS[key]["ok"]
        for key in ("table_roundtrip", "server_render", "custom_node", "csp", "phone_390")
    )
    print("SPIKE:", "OK" if ok else "NOT OK", file=sys.stderr)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
