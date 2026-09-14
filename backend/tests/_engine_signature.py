"""What `build_query` is allowed to take, in one place (#917).

Three tests guard this signature, from three different angles: the role fence is
not half-built (#832 §7.3), identity resolves one layer up and not here (#847),
and the engine takes no roles at all. They are three reasons, all worth keeping —
but they were three copies of one assertion, and adding `with_entities` for CR-07
meant editing the same line in three files.

Two of the same repair is the duplication talking (CLAUDE.md). So the list lives
here and the three tests say why it matters, each in their own words.

Adding a parameter is allowed; it just has to pass through this file, which is the
whole mechanism. The question to ask is not "is it needed?" but **"does it change
what you may see?"** — `tenant_id` does and is the fence; a role or a viewer would
and is refused; `with_entities` does not, it changes the shape a row comes back
in (CR-07 §5.2).
"""
import inspect

ALLOWED = {"selection", "tenant_id", "with_entities"}


def assert_engine_signature() -> None:
    from app.domains.reporting.api import build_query

    gevonden = set(inspect.signature(build_query).parameters)
    assert gevonden == ALLOWED, (
        f"`build_query` neemt nu {sorted(gevonden)}, verwacht {sorted(ALLOWED)}. "
        "Verandert een nieuwe parameter WAT je mag zien, dan hoort hij hier niet "
        "— dat is een hek en hekken horen niet in de motor. Verandert hij alleen "
        "de VORM waarin een rij terugkomt, zet hem dan in `ALLOWED` mét de reden."
    )
