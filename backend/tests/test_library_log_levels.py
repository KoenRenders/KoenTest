"""#1828 — a library does not speak below WARNING in the application log.

A library's DEBUG and INFO are its wire talk: what it sends and receives, line by
line. The root logger carried `LOG_LEVEL`, and a library's logger has no level of
its own, so a process started with `LOG_LEVEL=DEBUG` wrote all of it into the
application log. `configure_logging` now sets the levels in one place: the
application's own loggers follow `LOG_LEVEL`, everything else stands at WARNING.

**The loggers are found, not listed.** The test walks every logger that exists
after `app.main` and the application's lazily imported providers are loaded, and
adds the names a library makes only when it first connects — plus a name no
library has, because the rule is "everything that is not the application's", not
a list. It runs with the worst setting an environment can have, `LOG_LEVEL=DEBUG`,
and with the file handler attached: it reads what stands in the file and what went
to stdout.

Proven red, each by one edit that was put back:

- the root logger given `level` again in `basicConfig` → the walk fails, naming
  the library loggers that wrote DEBUG and INFO to the file and to stdout;
- the loop that takes back a level somebody else set taken out → the walk fails
  on the loggers the suite's own in-process migration put at INFO;
- `logging.getLogger(OWN_LOGGER).setLevel(level)` taken out → the application's
  own DEBUG line is missing from the file.

Naming a library below INFO is refused by `configure_logging` itself; the last
test holds that.
"""

import importlib
import io
import logging

import pytest

import app.main  # noqa: F401 — the loggers that exist once the application is loaded
from app.config import settings
from app.logging_config import LIBRARY_LEVEL, LIBRARY_LEVELS, configure_logging, is_own

pytestmark = pytest.mark.ui_agnostisch

#: Modules the application imports only when a provider is first used; importing them
#: here makes their libraries' loggers exist, as they do in a running server.
LAZY_MODULES = (
    "app.domains.chatbot.stt.providers.voxtral",
    "websockets.asyncio.client",
)
#: Loggers a library makes at its first connection, and one that no library has.
MADE_LATER = (
    "websockets.client",
    "httpcore.http11",
    "httpcore.connection",
    "a.library.nobody.imported.yet",
)
#: The libraries the issue names; the floor of the walk (#678: a walk that finds
#: nothing is green forever).
AT_LEAST = {"websockets", "httpcore", "httpx", "fontTools", "PIL", "pypdfium2"}


def library_level(name: str) -> int:
    """The level a library's logger stands at: the nearest name in
    `LIBRARY_LEVELS`, or `LIBRARY_LEVEL`."""
    while name:
        if name in LIBRARY_LEVELS:
            return LIBRARY_LEVELS[name][0]
        name = name.rpartition(".")[0]
    return LIBRARY_LEVEL


def _library_loggers() -> list[str]:
    for module in LAZY_MODULES:
        importlib.import_module(module)
    names = {name for name in logging.root.manager.loggerDict if not is_own(name)}
    return sorted(names | set(MADE_LATER))


@pytest.fixture
def log(tmp_path, monkeypatch):
    """The application's logging at its loudest setting, file handler attached.
    Returns a function that gives `(file text, stdout text)`."""
    stdout = io.StringIO()
    monkeypatch.setattr(settings, "app_log_dir", str(tmp_path))
    monkeypatch.setattr(settings, "log_level", "DEBUG")
    monkeypatch.setattr("sys.stdout", stdout)
    configure_logging()

    def read() -> tuple[str, str]:
        for handler in logging.getLogger().handlers:
            handler.flush()
        return (tmp_path / "app.log").read_text(), stdout.getvalue()

    yield read
    monkeypatch.undo()
    configure_logging()


def test_the_walk_finds_the_libraries_it_must_guard():
    tops = {name.split(".")[0] for name in _library_loggers()}
    assert AT_LEAST <= tops, f"the walk does not see {sorted(AT_LEAST - tops)}"
    assert len(_library_loggers()) > 50, "the walk found hardly a logger — it guards nothing"


def test_no_library_writes_below_warning_into_the_application_log(log):
    names = _library_loggers()
    for name in names:
        logger = logging.getLogger(name)
        logger.debug("wire-talk-debug")
        logger.info("wire-talk-info")
        logger.warning("library-warning")
    own = logging.getLogger("app.somewhere")
    own.debug("own-debug")
    file_text, stdout_text = log()

    for where, text in (("the file", file_text), ("stdout", stdout_text)):
        spoke = sorted(
            {
                name
                for _stamp, level, name in _wire_talk(text)
                if logging.getLevelName(level) < library_level(name)
            }
        )
        assert not spoke, (
            f"{len(spoke)} library loggers wrote below their level to {where}: {spoke[:8]}"
        )
        assert not [name for _s, level, name in _wire_talk(text) if level == "DEBUG"], (
            f"a library's DEBUG reached {where}"
        )
        assert "DEBUG app.somewhere: own-debug" in text, f"LOG_LEVEL no longer reaches {where}"
        heard = sum("library-warning" in line for line in text.splitlines())
        # A library whose logger does not propagate, or that is named above WARNING,
        # keeps its warning to itself; the others must all be heard.
        silent = [
            name
            for name in names
            if not logging.getLogger(name).isEnabledFor(logging.WARNING)
            or not _reaches_root(logging.getLogger(name))
        ]
        assert heard == len(names) - len(silent), f"{where}: a library's WARNING is lost"


def _wire_talk(text: str) -> list[tuple[str, str, str]]:
    """`(timestamp, level, logger)` of every line a library wrote below WARNING."""
    return [
        (stamp, level, name.rstrip(":"))
        for stamp, level, name, *_rest in (
            line.split(" ") for line in text.splitlines() if "wire-talk-" in line
        )
    ]


def _reaches_root(logger: logging.Logger) -> bool:
    current: logging.Logger | None = logger
    while current is not None and current is not logging.root:
        if not current.propagate:
            return False
        current = current.parent
    return True


def test_a_library_is_never_named_below_info(monkeypatch):
    for name, (lowest, why) in LIBRARY_LEVELS.items():
        assert lowest >= logging.INFO and why.strip(), name
    monkeypatch.setitem(LIBRARY_LEVELS, "websockets.client", (logging.DEBUG, "to look once"))
    try:
        with pytest.raises(ValueError, match="never logs below INFO"):
            configure_logging()
    finally:
        monkeypatch.undo()
        configure_logging()
