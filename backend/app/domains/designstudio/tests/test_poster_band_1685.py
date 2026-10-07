"""The poster's bottom band is no higher than it needs (#1685).

Koen, 7 October 2026: the registration sentence with the website took two rows
of the band ("Inschrijven tot en met … via" / "www.<site>"), and with three
organisers the band pushed the label and the text up. Now the site's name
stands under the QR code and the deadline is one row.

This turns Koen's own sentence of 21 September ("dat hoort samen") around. Its
reason still holds and is asserted here: the registration row keeps its ticket
and its accent colour, comes after the organisers, and the poster still says
where to register — through the code and the address under it.

Measured before building: the code's box is 28 mm with 44 mm for a line centred
under it; at the size that was asked (4.9 mm) "www.example.com" is 49 mm. Hence
the name without "www.", as large as fits down to 3.8 mm, then two lines.

Broken on purpose (7 October 2026): "via" kept on the deadline row → the rows
test; the website row kept in the left column → the same; "www." kept → the
caption tests; the two-line split taken out → the long name is one line wider
than its box; the band's height taken from the left column alone → a poster
with one row and a two-line name puts the name outside the band.
"""

from __future__ import annotations

import pytest

from app.domains.designstudio import brand, render, richtext
from app.domains.designstudio.blocks import (
    BAND_CONT_STEP,
    QR_BLOCK,
    QR_CAPTION_MAX,
    QR_CAPTION_MIN,
    QR_CAPTION_W,
    plan_affiche,
    site_caption,
)
from app.domains.designstudio.content import Contact, PosterContent

PAL = brand.palette_for("dark_green-golden_yellow")
LONGEST = "Inschrijven tot en met 30 september"


def _plan(*, organisers: int = 1, has_qr: bool = True, layout: str = "print_a", **more):
    fields = dict(
        duo_code="dark_green-golden_yellow",
        preset="eenvoudig",
        title_lines=("BOWLEN",),
        date_line="VRIJDAG 20 NOVEMBER OM 19U",
        location="DE KEGELBAAN",
        deadline_text=LONGEST,
        website="www.example.com",
        contacts=tuple(
            Contact(f"Voornaam Naam{i}", "0470 00 00 00", f"voornaam{i}@example.com")
            for i in range(organisers)
        ),
    )
    content = PosterContent(**(fields | more))
    height = 420 if layout == "print_a" else 371.25
    return plan_affiche(content, layout=layout, width=297, height=height, pal=PAL, has_qr=has_qr)


def _rows(plan) -> list[tuple[str, str, str]]:
    return [(str(r["id"]), str(r["icon"]), str(r["text"])) for r in plan.band["rows"]]


def test_with_a_deadline_the_row_is_one_line_and_the_site_stands_under_the_code():
    plan = _plan()
    assert _rows(plan)[-1] == ("t-deadline", "ticket", LONGEST), "the deadline row is not alone"
    assert not [r for r in plan.band["rows"] if r["id"] == "t-website"]
    assert plan.band["qr_site"] == ["example.com"]
    # the reason of 21 September: the row is the call to action, after the organisers
    last = plan.band["rows"][-1]
    assert last["colour"] == PAL["accent"] and plan.band["rows"][0]["icon"] == "users"


def test_without_a_shared_deadline_the_row_that_says_inschrijven_stays():
    plan = _plan(deadline_text="")
    assert _rows(plan)[-1] == ("t-website", "ticket", "Inschrijven via www.example.com")
    assert plan.band["qr_site"] == ["example.com"]


def test_without_registration_the_address_is_under_the_code_and_not_in_the_rows():
    plan = _plan(registration=False, deadline_text="")
    assert [r for r in plan.band["rows"] if r["id"] in ("t-website", "t-deadline")] == []
    assert plan.band["qr_site"] == ["example.com"]


def test_a_poster_without_a_code_keeps_the_sentence_it_had():
    """No code, no place under it: the two rows of before."""
    plan = _plan(has_qr=False)
    assert _rows(plan)[-2:] == [
        ("t-deadline", "ticket", f"{LONGEST} via"),
        ("t-website", "", "www.example.com"),
    ]
    assert plan.band["qr_site"] == []


@pytest.mark.parametrize("layout", ["print_a", "feed_portrait"])
@pytest.mark.parametrize(("organisers", "before"), [(1, 46.4), (2, 59.6), (3, 72.8)])
def test_the_band_is_a_row_lower_and_never_under_its_minimum(layout, organisers, before):
    """`before` is the band's height measured on the old code, in millimetres."""
    old = _plan(organisers=organisers, has_qr=False, layout=layout).band["h"]
    new = _plan(organisers=organisers, layout=layout).band["h"]
    print(f"MEASURE band {layout} organisers={organisers}: {old:.1f} -> {new:.1f} mm")
    assert old == pytest.approx(before, abs=0.05)
    assert old - new == pytest.approx(BAND_CONT_STEP, abs=0.05), (
        "the band did not lose exactly its continuation row"
    )
    assert new >= QR_BLOCK + 2


def test_the_deadline_row_fits_its_column_with_the_longest_month():
    plan = _plan(organisers=3)
    width = richtext.text_width(LONGEST, 5.6)
    assert width <= plan.boxes["t-deadline"], (width, plan.boxes["t-deadline"])
    assert next(r for r in plan.band["rows"] if r["id"] == "t-deadline")["size"] == 5.6


@pytest.mark.parametrize(
    ("website", "lines"),
    [
        ("www.example.com", ["example.com"]),
        ("example.com", ["example.com"]),
        ("WWW.Example.com", ["Example.com"]),
        # too wide for one line at the smallest size: two, broken at a dot
        ("www.raakvoorbeeld.example.com", ["raakvoorbeeld", ".example.com"]),
        ("", []),
    ],
)
def test_the_sites_name_under_the_code(website, lines):
    found, size = site_caption(website)
    assert found == lines
    assert QR_CAPTION_MIN <= size <= QR_CAPTION_MAX
    for line in found:
        assert richtext.text_width(line, size, bold=True) <= QR_CAPTION_W, (line, size)


def test_a_name_is_as_large_as_fits_and_no_larger():
    short, long = site_caption("www.abc.be")[1], site_caption("www.raakvoorbeelden.be")
    assert short == QR_CAPTION_MAX
    assert long[0] == ["raakvoorbeelden.be"], "this name fits one line"
    assert QR_CAPTION_MIN <= long[1] < QR_CAPTION_MAX
    assert richtext.text_width(long[0][0], long[1] + 0.1, bold=True) > QR_CAPTION_W


def test_a_two_line_name_stays_inside_the_band_also_with_one_row():
    """The band follows its taller column: here the code's."""
    plan = _plan(
        organisers=0,
        deadline_text="",
        registration=False,
        website="www.raakvoorbeeldafdeling.example.com",
    )
    band = plan.band
    assert len(band["qr_site"]) == 2
    last_baseline = band["qr_y"] + band["qr_box"] + 4.6 + band["qr_site_step"]
    assert band["qr_y"] >= band["y"] and last_baseline + 1 <= band["y"] + band["h"], band


def test_the_rendered_poster_shows_the_name_and_passes_the_overflow_check():
    merged = render.merge(
        PosterContent(
            duo_code="dark_green-golden_yellow",
            preset="eenvoudig",
            title_lines=("BOWLEN",),
            deadline_text=LONGEST,
            website="www.raakvoorbeeldafdeling.example.com",
            contacts=(Contact("Voornaam Naam", "0470 00 00 00", "voornaam@example.com"),),
        ),
        layout="print_a",
        qr_url="https://www.example.com/x",
    )
    assert ">raakvoorbeeldafdeling</text>" in merged.svg and ">.example.com</text>" in merged.svg
    assert "Scan voor meer info" not in merged.svg and " via<" not in merged.svg
    assert render.check(merged) == []


def test_the_rows_on_the_left_end_before_the_name_under_the_code():
    """The name's box is wider than the code: a row that ran on to the code's
    edge, as before, would stand under the name's first letters."""
    plan = _plan(organisers=3)
    band = plan.band
    name_left = band["qr_x"] + band["qr_box"] / 2 - QR_CAPTION_W / 2
    for row in band["rows"]:
        assert band["text_x"] + plan.boxes[str(row["id"])] <= name_left, row["id"]
    without = _plan(organisers=3, has_qr=False)
    assert without.boxes["t-deadline"] > plan.boxes["t-deadline"], "nothing to tell apart"
