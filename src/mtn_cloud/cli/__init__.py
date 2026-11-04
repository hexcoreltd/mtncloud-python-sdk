"""mtncloud command line interface entry point.

Typer is imported lazily so that ``import mtn_cloud`` never loads it.
"""

from __future__ import annotations

import os
import sys
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtn_cloud import ClientSettings, MtnCloudClient

    ClientFactory = Callable[[ClientSettings], MtnCloudClient]

__all__ = ["main"]

_INSTALL_HINT = 'mtncloud requires the CLI extra: pip install "mtncloud-python-sdk[cli]"'


def _silence_stdout() -> None:
    """Point stdout at devnull so the interpreter does not fail flushing at exit."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass


def main(
    argv: list[str] | None = None,
    *,
    client_factory: ClientFactory | None = None,
    now: Callable[[], datetime] | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        import typer

        from mtn_cloud.cli import app as app_module
    except ImportError:
        sys.stderr.write(_INSTALL_HINT + "\n")
        return 2

    from mtn_cloud import MtnCloudClient
    from mtn_cloud.cli import output
    from mtn_cloud.cli.errors import (
        EXIT_INTERNAL,
        EXIT_INTERRUPTED,
        EXIT_USAGE,
        exit_code_for,
    )

    def default_factory(settings: ClientSettings) -> MtnCloudClient:
        return MtnCloudClient(settings=settings)

    state = app_module.CliState()
    cli_app = app_module.build_app(
        client_factory=client_factory or default_factory,
        now=now or (lambda: datetime.now(timezone.utc)),
        state=state,
    )
    if not args:
        args = ["--help"]
    original_stdout, original_stderr = sys.stdout, sys.stderr
    try:
        try:
            result = cli_app(args=args, prog_name="mtncloud", standalone_mode=False)
        except SystemExit as exc:
            # Typer converts a real EPIPE into sys.exit(1) after swapping in flush wrappers.
            if sys.stdout is not original_stdout:
                sys.stdout, sys.stderr = original_stdout, original_stderr
                _silence_stdout()
                return 0
            code = exc.code
            if code is None:
                return 0
            return code if isinstance(code, int) else EXIT_INTERNAL
        return result if isinstance(result, int) else 0
    except typer.Exit as exc:
        return exc.exit_code
    except typer.Abort:
        sys.stderr.write("Aborted.\n")
        return EXIT_INTERRUPTED
    except typer.exceptions.TyperException as exc:
        show = getattr(exc, "show", None)
        if show is not None:
            show()
        else:
            sys.stderr.write(f"Error: {exc.message}\n")
        return EXIT_USAGE
    except BrokenPipeError:
        _silence_stdout()
        return 0
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except Exception as exc:
        fmt = state.fmt or output.resolve_format(None)
        try:
            output.emit_error(exc, fmt)
            if state.debug:
                sys.stderr.write(traceback.format_exc())
        except BrokenPipeError:
            pass
        code = exit_code_for(exc)
        return code if code else EXIT_INTERNAL
