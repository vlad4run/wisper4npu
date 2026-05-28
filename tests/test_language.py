"""Language set / cycle logic on the daemon (no asyncio, no real mic)."""
from __future__ import annotations

import pytest

from flm_voice.config import Config
from flm_voice.daemon import Daemon


@pytest.fixture(autouse=True)
def _silence_notify(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("flm_voice.output.notify", lambda *a, **kw: None)


def test_set_explicit_language() -> None:
    daemon = Daemon(Config(language=None, languages=["ru", "en"]))
    daemon._set_language("ru")
    assert daemon.cfg.language == "ru"


def test_set_auto_clears_language() -> None:
    daemon = Daemon(Config(language="ru", languages=["ru", "en"]))
    daemon._set_language("auto")
    assert daemon.cfg.language is None


def test_set_none_clears_language() -> None:
    daemon = Daemon(Config(language="ru", languages=["ru", "en"]))
    daemon._set_language(None)
    assert daemon.cfg.language is None


def test_cycle_from_first_advances() -> None:
    daemon = Daemon(Config(language="ru", languages=["ru", "en"]))
    daemon._cycle_language()
    assert daemon.cfg.language == "en"


def test_cycle_wraps_around() -> None:
    daemon = Daemon(Config(language="en", languages=["ru", "en"]))
    daemon._cycle_language()
    assert daemon.cfg.language == "ru"


def test_cycle_from_unknown_starts_at_first() -> None:
    daemon = Daemon(Config(language="fr", languages=["ru", "en"]))
    daemon._cycle_language()
    assert daemon.cfg.language == "ru"


def test_cycle_includes_auto_when_listed() -> None:
    daemon = Daemon(Config(language="ru", languages=["ru", "en", "auto"]))
    daemon._cycle_language()
    assert daemon.cfg.language == "en"
    daemon._cycle_language()
    assert daemon.cfg.language is None
    daemon._cycle_language()
    assert daemon.cfg.language == "ru"


def test_cycle_with_empty_list_is_noop() -> None:
    daemon = Daemon(Config(language="ru", languages=[]))
    daemon._cycle_language()
    assert daemon.cfg.language == "ru"
