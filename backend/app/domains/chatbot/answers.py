"""An answer in a fixed shape: asked for as JSON, parsed in one place, retried once (#1968).

Wherever Raakje must answer with a JSON object — the newsletter's proposal and
its verification round, the activity's proposal and its verification — the
caller goes through `json_answer`, and so follows one rule:

1. **the call asks for JSON** through the provider's own setting
   (`complete(..., json_answer=True)`), beside the sentence in the prompt;
2. **one retry** when the answer does not parse: the request once more, before
   anybody sees a message — not a loop;
3. **the failure is logged without content**: which surface and capability,
   which attempt, the answer's length and the parser's reason, never a word of
   the answer. A failure the retry repaired is logged too: that line is how we
   learn how often the model breaks the shape.

The log is the backend log, not the AI call log: that log writes its row when
the call leaves, before anybody parses, and has no column for what came back.

**The tool loop.** A proposal that reads through tools (`run_chat`) gets its
answer from a call that also offers the tools. Whether the provider accepts its
JSON setting together with tools is not measured (13 October 2026: no test may
call the real provider), so those rounds go out as before, and their final
answer comes in as `first`. When it does not parse, the retry is one call
without tools and with the setting, on the conversation as it stands — the tool
results are in it, and no tool runs twice.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

NO_OBJECT = "no object found"
NOT_AN_OBJECT = "not an object"


class UnusableAnswer(Exception):
    """The model's answer is not a JSON object; `reason` says why, without the answer."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def parse_json_object(text: str | None) -> dict[str, Any]:
    """The JSON object in an answer — also when prose or a code fence stands
    around it. Raises `UnusableAnswer` with the reason: no object found, invalid
    at position n, or not an object."""
    text = text or ""
    # The whole answer first: valid JSON that is a list or a word is no object,
    # and the object inside a list is not the answer that was asked for.
    try:
        whole = json.loads(text)
    except json.JSONDecodeError:
        pass
    else:
        if isinstance(whole, dict):
            return whole
        raise UnusableAnswer(NOT_AN_OBJECT)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise UnusableAnswer(NO_OBJECT)
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise UnusableAnswer(f"invalid at position {start + exc.pos}") from None
    if not isinstance(data, dict):
        raise UnusableAnswer(NOT_AN_OBJECT)
    return data


def _where(provider: Any) -> str:
    """Surface and capability of the call, as the guarded provider knows them."""
    return getattr(provider, "log_name", None) or getattr(provider, "name", "") or "-"


def _ask(provider: Any, messages: list[dict[str, Any]], fields: Any = ()) -> str:
    # `fields` (CR-33 F6) go to the guarded provider as they are; a provider that is not
    # the seam is never offered them.
    extra = {"fields": fields} if fields else {}
    return provider.complete(messages, tools=None, json_answer=True, **extra).content or ""


def json_answer(
    provider: Any, messages: list[dict[str, Any]], *, first: str | None = None, fields: Any = ()
) -> dict[str, Any]:
    """The model's answer to `messages` as a JSON object, by the one rule above.

    `first` is an answer already in hand — the final answer of a tool loop; then
    only the retry is a call of this function's own. Raises `UnusableAnswer` when
    the second answer does not parse either; a refusal of the guard and a failure
    of the provider pass through as they are."""
    text = _ask(provider, messages, fields) if first is None else first
    try:
        return parse_json_object(text)
    except UnusableAnswer as fault:
        logger.warning(
            "Raakje's answer did not parse (%s): attempt 1 of 2, %d characters, %s",
            _where(provider),
            len(text),
            fault.reason,
        )
    text = _ask(provider, messages, fields)
    try:
        data = parse_json_object(text)
    except UnusableAnswer as fault:
        logger.warning(
            "Raakje's answer did not parse (%s): attempt 2 of 2, %d characters, %s",
            _where(provider),
            len(text),
            fault.reason,
        )
        raise
    logger.warning("Raakje's answer parsed on the retry (%s)", _where(provider))
    return data
