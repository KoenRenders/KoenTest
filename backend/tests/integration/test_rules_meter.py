"""The meter of CR-13 (§A2, §B9.2, requirement R7) — phase 0a.

The numbers of the change request's as-is table, measured by the gate on every
run instead of counted by hand, so each release issue can show them and each one
can only move the right way. `pytest -s -k a2_numbers` prints the table.

The counts reuse the collectors of `test_rules_gate.py`, so a number here and a
verdict there can never disagree. Phase 0c adds its rows (promises, foreign
writes, commits outside the door service, …).
"""

from __future__ import annotations

import ast

from tests.test_rules_gate import (
    SHAPE,
    _api_routes,
    _mappers,
    _packages,
    _python_files,
    _tree,
    collect_command_calls_outside_handlers,
    collect_commit_behind_api,
    collect_commit_in_handler,
    collect_derived_value_elsewhere,
    collect_dutch_identifiers,
    collect_foreign_writes,
    collect_json_route_without_caller,
    collect_network_in_handler,
    collect_non_orm_writes,
    collect_promises,
    collect_rule_in_router,
    collect_session_on_entity,
    collect_validator_without_constraint,
    collect_write_after_commit,
    collect_write_outside_service,
)


def count_validators(mappers=None) -> int:
    """Attribute validators (`@validates`) over all mapped classes."""
    return sum(len(m.validators) for m in (mappers if mappers is not None else _mappers()))


def _enum_counts() -> tuple[int, int, int]:
    """(CodeEnum, TechnicalEnum, str-mixin Enum that is neither)."""
    from enum import Enum

    import app.domains.payment.providers.mollie  # noqa: F401 — the adapter enum
    import app.domains.reporting.engine  # noqa: F401 — the technical enums
    import app.domains.reporting.universe  # noqa: F401
    from app.kernel.codes import CodeEnum, ExternalVocabulary, TechnicalEnum

    _mappers()

    def subclasses(cls):
        out, todo = set(), [cls]
        while todo:
            for sub in todo.pop().__subclasses__():
                if sub not in out:
                    out.add(sub)
                    todo.append(sub)
        return out

    code = {c for c in subclasses(CodeEnum) if c is not ExternalVocabulary}
    technical = subclasses(TechnicalEnum)
    loose = {
        c
        for c in subclasses(Enum)
        if issubclass(c, str)
        and c.__module__.startswith("app.")
        and c not in technical
        and not issubclass(c, CodeEnum)
    }
    return len(code), len(technical), len(loose)


def _untyped_db_parameters() -> int:
    count = 0
    for path in _python_files():
        for node in ast.walk(_tree(path)):
            if isinstance(node, ast.arg) and node.arg == "db" and node.annotation is None:
                count += 1
    return count


def _exception_classes() -> tuple[int, int, int]:
    """(`*Fout` classes, `*Error` classes, `*Fout` aliases of an `*Error`) under app/."""
    fout = error = alias = 0
    for path in _python_files():
        for node in _tree(path).body:
            if isinstance(node, ast.ClassDef):
                fout += node.name.endswith("Fout")
                error += node.name.endswith("Error")
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
                if node.value.id.endswith("Error") and any(
                    isinstance(t, ast.Name) and t.id.endswith("Fout") for t in node.targets
                ):
                    alias += 1
    return fout, error, alias


def a2_table() -> list[tuple[str, int | str]]:
    """The numbers of CR-13 §A2/§B9.2, measured — the rows phase 0c extends."""
    from sqlalchemy import CheckConstraint

    mappers = _mappers()
    checks = sum(isinstance(c, CheckConstraint) for m in mappers for c in m.local_table.constraints)
    code, technical, loose = _enum_counts()
    fout, error, alias = _exception_classes()
    packages = _packages()
    shape = {
        piece: sum(
            ((p / piece.rstrip("/")).is_dir() if piece.endswith("/") else (p / piece).is_file())
            for p in packages
        )
        for piece in SHAPE
    }
    routes = _api_routes()
    return [
        ("attribute validators (@validates)", count_validators(mappers)),
        ("CheckConstraint on models", checks),
        (
            "enums: CodeEnum / TechnicalEnum / str-Enum outside both",
            f"{code} / {technical} / {loose}",
        ),
        ("db parameters without a type", _untyped_db_parameters()),
        ("models.py touching a session", len(collect_session_on_entity())),
        (
            "exception classes: *Fout / *Error / *Fout alias of an *Error",
            f"{fout} / {error} / {alias}",
        ),
        (
            f"domain packages with api.py / codes.py / CONTRACT.md / tests/ (of {len(packages)})",
            f"{shape['api.py']} / {shape['codes.py']} / {shape['CONTRACT.md']} / {shape['tests/']}",
        ),
        (
            "JSON routes, method × path / without a named caller",
            f"{len(routes)} / {len(collect_json_route_without_caller())}",
        ),
        (
            "event handlers that commit / reach the network",
            f"{len(collect_commit_in_handler())} / {len(collect_network_in_handler())}",
        ),
        ("validators without their constraint", len(collect_validator_without_constraint(mappers))),
        ("Dutch identifiers (#780)", len(collect_dutch_identifiers())),
        ("writes to another domain's classes (function × class)", len(collect_foreign_writes())),
        (
            "functions that write after a commit / api functions that commit for another domain",
            f"{len(collect_write_after_commit())} / {len(collect_commit_behind_api())}",
        ),
        (
            "calls into another domain's command outside a handler",
            len(collect_command_calls_outside_handlers()),
        ),
        ("refusals decided in a router or screen", len(collect_rule_in_router())),
        (
            "writes outside a service / past the ORM",
            f"{len(collect_write_outside_service())} / {len(collect_non_orm_writes())}",
        ),
        ("derived values computed outside their owner", len(collect_derived_value_elsewhere())),
        (
            "template promises not kept / not walkable",
            "{} / {}".format(*(len(part) for part in collect_promises())),
        ),
    ]


def test_the_a2_numbers_are_measured_and_printed(capsys):
    """R7: the numbers come out of the gate, not out of the document.

    Run `pytest -s -k a2_numbers` and paste the output into the release issue.
    Each number must be equal to or better than the previous release's.
    """
    rows = a2_table()
    with capsys.disabled():
        print("\n\nCR-13 §A2 — measured by the gate\n")
        for name, value in rows:
            print(f"  {str(value):>14}  {name}")
        print()
    assert rows and all(value != "" for _, value in rows)


def test_the_validator_count_moves():
    """§B8 test 9: add one `@validates` and the count rises by exactly one — a
    meter, not a picture. Proven on a class of its own, next to the real ones."""
    from sqlalchemy import Column, Integer, String
    from sqlalchemy.orm import declarative_base, validates

    real = _mappers()
    Base = declarative_base()

    class OneRule(Base):
        __tablename__ = "rules_gate_one_rule"
        id = Column(Integer, primary_key=True)
        name = Column(String, nullable=False)

        @validates("name")
        def _name(self, key, value):
            return value

    assert count_validators(real + list(Base.registry.mappers)) == count_validators(real) + 1
