"""Structured values for a model, by attribute (CR-33 F5, F6, F7).

A module that composes a prompt from stored values used to format them itself
(`f"Naam: {activity.name}"`), so what went to the model was decided in each module.
It hands pairs now — `(attribute key, value)` — and the port renders them AFTER the
classification of each key for the surface of the call:

- **public** passes on both surfaces;
- **internal** passes on the back-office surface and is refused on the public one;
- **tokenised** is never sent as its value: on the back-office surface the caller's
  entity token (`persoon-90`) is, and without one the key is refused; on the public
  surface it is refused;
- **none** is refused, everywhere, before the call;
- a key the register does not know is refused.

A refusal is a `FieldRefused` (a `SeamBlocked`: its message is for the screen), names
the KEY and never the value, and is logged in the AI log as a blocked call
(`GuardedProvider.complete`). What stays outside is free text a person wrote — an
instruction, a letter, a page — which has no key and keeps the pattern guard
(`seam.refusal`); the pattern guard also stays on the rendered block as the second net.

The text is rendered as `label: value` lines, the label the register's; the back-office
surface also has the known name parts scrubbed (`scrub_names`, the placeholder `[naam]`),
as the callers did by hand before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from app.kernel.attributes import AiExposure, attribute

from .models import AiSurface
from .seam import GuardRules, SeamBlocked, scrub_names

#: Where a call's rendered fields stand in its messages: a message that holds this
#: text gets the block in its place; without one the block is appended to the last
#: message of the reader.
FIELDS_MARK = "{{fields}}"

NAME_PLACEHOLDER = "[naam]"


@dataclass(frozen=True)
class Field:
    """One stored value, named by its attribute. `token` is the entity token
    (`persoon-90`) a TOKENISED attribute goes as; the value itself never does."""

    key: str
    value: str
    token: str = ""


class FieldRefused(SeamBlocked):
    """The register does not let this key go to a model on this surface."""

    def __init__(self, key: str, why: str, message: str) -> None:
        super().__init__(message)
        self.key = key
        self.why = why


def coerce(item: Any) -> Field:
    """A `Field`, or a `(key, value)` / `(key, value, token)` tuple as one."""
    if isinstance(item, Field):
        return item
    key, value, *rest = item
    return Field(str(key), "" if value is None else str(value), rest[0] if rest else "")


def render_fields(fields: Iterable[Any], rules: GuardRules) -> str:
    """The block of `label: value` lines the model reads, after the classification
    of every key for `rules.surface`. Raises `FieldRefused` for the first key that
    may not go."""
    lines: list[str] = []
    for item in fields:
        one = coerce(item)
        try:
            entry = attribute(one.key)
        except LookupError:
            raise FieldRefused(
                one.key,
                "unknown",
                f"Dit is niet verstuurd: '{one.key}' staat niet in het register van gegevens.",
            ) from None
        level = entry.ai_exposure
        word = entry.text
        if level is AiExposure.NONE:
            raise FieldRefused(
                one.key,
                level.value,
                f"Dit is niet verstuurd: '{word}' gaat nooit naar het taalmodel.",
            )
        if rules.surface is AiSurface.PUBLIC and level is not AiExposure.PUBLIC:
            raise FieldRefused(
                one.key,
                level.value,
                f"Dat is niet verstuurd: '{word}' is niet openbaar.",
            )
        shown = one.value
        if level is AiExposure.TOKENISED:
            if not one.token:
                raise FieldRefused(
                    one.key,
                    level.value,
                    f"Dit is niet verstuurd: '{word}' kan enkel als token, en er is er geen.",
                )
            shown = one.token
        lines.append(f"{word}: {shown.strip() or '(leeg)'}")
    block = "\n".join(lines)
    if rules.match_names:
        block = scrub_names(block, rules.names(), NAME_PLACEHOLDER)
    return block


def place_fields(messages: Sequence[dict[str, Any]], block: str) -> list[dict[str, Any]]:
    """The messages with the block in them: where `FIELDS_MARK` stands, else at the
    end of the last message of the reader. The caller's list is not changed."""
    placed = [dict(m) for m in messages]
    for message in placed:
        content = message.get("content")
        if isinstance(content, str) and FIELDS_MARK in content:
            message["content"] = content.replace(FIELDS_MARK, block, 1)
            return placed
    for message in reversed(placed):
        if message.get("role") == "user" and isinstance(message.get("content"), str):
            message["content"] = f"{message['content']}\n\n{block}"
            return placed
    placed.append({"role": "user", "content": block})
    return placed


@dataclass(frozen=True)
class NamedException:
    """A stored datum classified `none` that one named reader still sends to a model, and why.

    Koen, 15 October 2026 (Q&A nr. 12, question 1, "a"): the newsletter's writer reads the
    minutes as today, with the names removed; everywhere else the notes stay `nooit`. The
    exception stands HERE, once, with its reader and its reason, and the reader says so at the
    place where it reads (`use_named_exception`): a second reader is no exception, it is a
    second door."""

    key: str
    by: str
    reason: str


NAMED_EXCEPTIONS: dict[str, NamedException] = {
    "meetings.meeting_item.notes_document": NamedException(
        key="meetings.meeting_item.notes_document",
        by="newsletter.drafting",
        reason=(
            "the letter is written from the minutes: read as free text with the known name parts "
            "scrubbed, under the pattern guard (Koen, 15 October 2026, 'a')"
        ),
    ),
}


def use_named_exception(key: str, *, by: str) -> NamedException:
    """The exception for `key` when `by` is the reader it names; `LookupError` otherwise."""
    found = NAMED_EXCEPTIONS.get(key)
    if found is None or found.by != by:
        raise LookupError(
            f"{by} is no named exception for {key}: a datum of the register that is `none` goes to "
            f"a model through `fields` or through an exception named in chatbot/fields.py"
        )
    return found
