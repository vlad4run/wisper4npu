"""flm-voice CLI entry point: daemon | toggle | status | stop | oneshot."""
from __future__ import annotations

import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="flm-voice")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("daemon", help="Run the long-lived daemon (foreground; for systemd)")
    sub.add_parser("toggle", help="Toggle recording (start if idle, stop if recording)")
    sub.add_parser("status", help="Print daemon state as JSON")
    sub.add_parser("stop", help="Tell the daemon to exit cleanly")
    sub.add_parser("cancel", help="Discard the current recording without transcribing")
    one = sub.add_parser("oneshot", help="Record for N seconds and print transcript (no daemon)")
    one.add_argument("--duration", type=float, default=5.0)
    lang = sub.add_parser(
        "lang",
        help="Show / set / cycle the transcription language (no arg = show)",
    )
    lang.add_argument(
        "value",
        nargs="?",
        help="Language code (e.g. ru, en), 'auto', or 'next' to cycle through configured languages",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.cmd == "daemon":
        from flm_voice.daemon import run
        return run()

    if args.cmd in ("toggle", "status", "stop", "cancel"):
        from flm_voice.ipc import send_command
        return send_command(args.cmd)

    if args.cmd == "lang":
        from flm_voice.ipc import send_command
        if args.value is None:
            return send_command("status")
        if args.value == "next":
            return send_command("lang_next")
        return send_command("lang_set", value=args.value)

    if args.cmd == "oneshot":
        from flm_voice.recorder import record_to_wav
        from flm_voice.transcriber import transcribe_sync
        wav = record_to_wav(duration=args.duration)
        print(transcribe_sync(wav))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
