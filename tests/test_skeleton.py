"""Sanity checks: package imports cleanly, CLI builds, IPC fails gracefully."""
from __future__ import annotations

import pytest


def test_package_imports() -> None:
    from flm_voice import config, ipc, output  # noqa: F401
    from flm_voice import daemon, recorder, transcriber, vad  # noqa: F401


def test_cli_help_does_not_crash(capsys: pytest.CaptureFixture[str]) -> None:
    from flm_voice.__main__ import build_parser

    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0
    assert "flm-voice" in capsys.readouterr().out


def test_ipc_returns_2_when_no_daemon(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "flm_voice.ipc.socket_path", lambda: tmp_path / "missing.sock"
    )
    from flm_voice.ipc import send_command

    assert send_command("status") == 2
