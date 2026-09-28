"""View-models of the membership screens.

Most membership routes still pass a dict (they are on the layer gate's allowlist);
new routes get a view-model from the start (#643-F).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.ui.viewmodel import ViewModel


@dataclass(frozen=True, kw_only=True)
class EmailRowView(ViewModel):
    """One extra e-mail row on the Word lid form (#1246), rendered by
    `_email_rij.html`. The family does not exist yet, so the row has no id and
    no server actions (`basis_url`, `doel`, `swap` stay empty), and it is never
    the first row, so never the primary address."""

    rij: None = None
    index: int
    nummer: int
    name_prefix: str
    first: bool = False
    required: bool = False
    basis_url: str = ""
    doel: str = ""
    swap: str = ""
