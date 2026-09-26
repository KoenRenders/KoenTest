"""The code list the reporting domain owns (CR-12 phase 4).

One list: what an export took out. Nothing shows it on a screen yet — the
export log is an audit trail — but it is a closed vocabulary that a column
stores, so it gets the shape every other one has, and its words are ready the
day a screen lists the exports.
"""
from app.domains.reporting.models import ExportKind, ExportKindCode, ExportKindLabel
from app.kernel.codes import CodeList, CodeSeed

EXPORT_KIND_CODES = (
    CodeSeed(code="report", nl="Rapport", en="Report", sort_order=10),
    CodeSeed(code="ad-hoc", nl="Losse opvraging", en="Ad-hoc query", sort_order=20),
    CodeSeed(code="dataset", nl="Dataset", en="Dataset", sort_order=30),
)

EXPORT_KIND = CodeList(
    name="export_kind", schema="reporting",
    codes=ExportKindCode, labels=ExportKindLabel, enum=ExportKind,
    fk_from=("reporting.export_log.kind",),
)
