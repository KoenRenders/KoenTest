"""Gedeelde OpenDocument Spreadsheet (.ods) export (#200).

Vendor-neutrale open standaard (ISO/IEC 26300), bewerkbaar in LibreOffice Calc, met
basis-layout (vette kop met vulling, kolombreedtes). Vervangt de eerdere .xlsx-export.
"""
from io import BytesIO

from odf.opendocument import OpenDocumentSpreadsheet
from odf.style import (
    Style,
    TableCellProperties,
    TableColumnProperties,
    TextProperties,
)
from odf.table import Table, TableCell, TableColumn, TableRow
from odf.text import P


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _cell(value, stylename=None):
    if _is_number(value):
        cell = TableCell(valuetype="float", value=str(value), stylename=stylename) \
            if stylename else TableCell(valuetype="float", value=str(value))
        cell.addElement(P(text=str(value)))
    else:
        # Native .ods: elke cel is type "string" en wordt door Calc/Excel nooit als
        # formule uitgevoerd — dat celtype IS de bescherming tegen formule-injectie
        # (#288). Geen apostrof-prefix: die hoort bij CSV en corrumpeerde hier
        # legitieme waarden (zichtbare ', mobiele nummers +32… → '+32…).
        text = "" if value is None else str(value)
        cell = TableCell(valuetype="string", stylename=stylename) \
            if stylename else TableCell(valuetype="string")
        cell.addElement(P(text=text))
    return cell


def build_ods(sheet_name: str, headers, rows, *, col_widths=None, bold_last_row=False) -> bytes:
    """Bouw een .ods met één blad: vette kopregel + datarijen. ``col_widths`` in cm,
    ``bold_last_row`` voor een totaalrij. Geeft de bytes terug."""
    doc = OpenDocumentSpreadsheet()

    header_style = Style(name="hdr", family="table-cell")
    header_style.addElement(TextProperties(fontweight="bold"))
    header_style.addElement(TableCellProperties(backgroundcolor="#E5E7EB"))
    doc.automaticstyles.addElement(header_style)

    bold_style = Style(name="bold", family="table-cell")
    bold_style.addElement(TextProperties(fontweight="bold"))
    doc.automaticstyles.addElement(bold_style)

    table = Table(name=(sheet_name or "Blad1")[:31])

    if col_widths:
        for i, w in enumerate(col_widths):
            cs = Style(name=f"col{i}", family="table-column")
            cs.addElement(TableColumnProperties(columnwidth=f"{w}cm"))
            doc.automaticstyles.addElement(cs)
            table.addElement(TableColumn(stylename=cs))

    hr = TableRow()
    for h in headers:
        cell = TableCell(valuetype="string", stylename=header_style)
        cell.addElement(P(text=str(h)))
        hr.addElement(cell)
    table.addElement(hr)

    rows = list(rows)
    for idx, row in enumerate(rows):
        last = bold_last_row and idx == len(rows) - 1
        tr = TableRow()
        for v in row:
            tr.addElement(_cell(v, stylename=bold_style if last else None))
        table.addElement(tr)

    doc.spreadsheet.addElement(table)
    buf = BytesIO()
    doc.write(buf)
    return buf.getvalue()
