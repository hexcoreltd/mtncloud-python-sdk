"""Typer application for the mtncloud CLI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import typer
from pydantic import ValidationError as PydanticValidationError

from mtn_cloud import ClientSettings, MtnCloudClient, __version__
from mtn_cloud.cli import output
from mtn_cloud.cli.errors import EXIT_OK, MissingCredentialsError
from mtn_cloud.cli.output import OutputFormat

ClientFactory = Callable[[ClientSettings], MtnCloudClient]

_FIELD_OPTIONS = {"base_url": "--base-url", "timeout": "--timeout"}


@dataclass
class CliState:
    """Mutable record of the parsed global options, readable by ``main`` after a failure."""

    fmt: OutputFormat | None = None
    debug: bool = False


@dataclass
class CliContext:
    fmt: OutputFormat
    settings: ClientSettings
    client_factory: ClientFactory
    now: Callable[[], datetime]

    def client(self) -> MtnCloudClient:
        """Build the client, failing before any request when no token is configured."""
        if self.settings.token_value() is None:
            raise MissingCredentialsError()
        return self.client_factory(self.settings)


def _build_settings(base_url: str | None, timeout: float | None) -> ClientSettings:
    overrides: dict[str, Any] = {}
    if base_url is not None:
        overrides["base_url"] = base_url
    if timeout is not None:
        overrides["timeout"] = timeout
    try:
        return ClientSettings(**overrides)
    except PydanticValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        first = str(exc.errors()[0]["loc"][0]) if exc.errors() else ""
        raise typer.BadParameter(
            f"invalid setting {details}", param_hint=_FIELD_OPTIONS.get(first)
        ) from None


def _validate_format(requested: str | None) -> OutputFormat:
    if requested is not None and requested not in ("json", "table"):
        raise typer.BadParameter("must be 'json' or 'table'", param_hint="--output")
    return output.resolve_format(requested)


def build_app(
    *, client_factory: ClientFactory, now: Callable[[], datetime], state: CliState | None = None
) -> typer.Typer:
    state = state if state is not None else CliState()
    app = typer.Typer(
        name="mtncloud",
        help="Read-only command line interface for MTN Cloud.",
        pretty_exceptions_enable=False,
        no_args_is_help=True,
        add_completion=False,
    )

    @app.callback()
    def root(
        ctx: typer.Context,
        output_format: str | None = typer.Option(  # noqa: UP007
            None, "-o", "--output", help="Output format: json or table."
        ),
        base_url: str | None = typer.Option(  # noqa: UP007
            None, "--base-url", help="Override the MTN Cloud base URL."
        ),
        timeout: float | None = typer.Option(  # noqa: UP007
            None, "--timeout", help="Request timeout in seconds."
        ),
        debug: bool = typer.Option(False, "--debug", help="Print a traceback on errors."),
    ) -> None:
        fmt = _validate_format(output_format)
        state.fmt = fmt
        state.debug = debug
        ctx.obj = CliContext(
            fmt=fmt,
            settings=_build_settings(base_url, timeout),
            client_factory=client_factory,
            now=now,
        )

    @app.command()
    def version(
        ctx: typer.Context,
        output_format: str | None = typer.Option(  # noqa: UP007
            None, "-o", "--output", help="Output format: json or table."
        ),
    ) -> int:
        """Print the SDK version."""
        cli: CliContext = ctx.obj
        if output_format is not None:
            cli.fmt = _validate_format(output_format)
            state.fmt = cli.fmt
        if cli.fmt == "json":
            output.emit_json({"schema": "mtncloud.version/v1", "version": __version__})
        else:
            typer.echo(f"mtncloud {__version__}")
        return EXIT_OK

    return app
