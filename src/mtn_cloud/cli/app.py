"""Typer application for the mtncloud CLI."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import typer
from pydantic import ValidationError as PydanticValidationError

from mtn_cloud import ClientSettings, MtnCloudClient, __version__
from mtn_cloud.cli import inventory as inventory_module
from mtn_cloud.cli import output
from mtn_cloud.cli.errors import EXIT_OK, AmbiguousNameError, MissingCredentialsError
from mtn_cloud.cli.output import OutputFormat
from mtn_cloud.cli.registry import REGISTRY, ResourceSpec
from mtn_cloud.cli.scope import is_id, resolve_scope
from mtn_cloud.modern_exceptions import AmbiguousLookupError, MtnCloudError

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


def _select_specs(only: str | None) -> list[ResourceSpec]:
    if only is None:
        return list(REGISTRY.values())
    names = [part.strip() for part in only.split(",") if part.strip()]
    unknown = [n for n in names if n not in REGISTRY]
    if unknown or not names:
        raise typer.BadParameter(
            f"unknown resource {', '.join(unknown) or only!r}; choose from {', '.join(REGISTRY)}",
            param_hint="--only",
        )
    return [spec for name, spec in REGISTRY.items() if name in names]


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

    @app.command()
    def inventory(
        ctx: typer.Context,
        only: str | None = typer.Option(  # noqa: UP007
            None, "--only", help="Comma-separated resources to include."
        ),
        group: str | None = typer.Option(None, "--group", help="Group name or ID."),  # noqa: UP007
        zone: str | None = typer.Option(None, "--zone", help="Zone name or ID."),  # noqa: UP007
        output_format: str | None = typer.Option(  # noqa: UP007
            None, "-o", "--output", help="Output format: json or table."
        ),
    ) -> int:
        """Snapshot every resource section; exit 3 if some sections fail."""
        cli: CliContext = ctx.obj
        if output_format is not None:
            cli.fmt = _validate_format(output_format)
            state.fmt = cli.fmt
        specs = _select_specs(only)
        client = cli.client()
        scope = resolve_scope(client, group=group, zone=zone)
        sections = inventory_module.collect_sections(client, scope, specs)
        document, code = inventory_module.build_inventory(
            client,
            scope,
            specs,
            base_url=str(cli.settings.base_url),
            now=cli.now,
            sections=sections,
        )
        failures = [r for _, r in sections if isinstance(r, MtnCloudError)]
        if sections and len(failures) == len(sections):
            # Every section failed: the command failed, so stdout stays empty.
            output.emit_error(failures[0], cli.fmt)
            return code
        if cli.fmt == "json":
            output.emit_json(document)
        else:
            for spec, result in sections:
                if isinstance(result, MtnCloudError):
                    output.emit_error(result, "table")
                else:
                    sys.stdout.write(f"{spec.name}\n")
                    output.emit_table(spec.columns, result)
        return code

    for spec in REGISTRY.values():
        app.add_typer(_resource_app(spec, state), name=spec.name)

    return app


def _resource_app(spec: ResourceSpec, state: CliState) -> typer.Typer:
    """Build the shared ``list`` and ``describe`` sub-app for one registry entry."""
    sub = typer.Typer(
        help=f"List and describe {spec.name}.",
        pretty_exceptions_enable=False,
        no_args_is_help=True,
        add_completion=False,
    )

    def apply_format(cli: CliContext, requested: str | None) -> None:
        if requested is not None:
            cli.fmt = _validate_format(requested)
            state.fmt = cli.fmt

    @sub.command("list")
    def list_(
        ctx: typer.Context,
        group: str | None = typer.Option(None, "--group", help="Group name or ID."),  # noqa: UP007
        zone: str | None = typer.Option(None, "--zone", help="Zone name or ID."),  # noqa: UP007
        name: str | None = typer.Option(None, "--name", help="Filter by name."),  # noqa: UP007
        output_format: str | None = typer.Option(  # noqa: UP007
            None, "-o", "--output", help="Output format: json or table."
        ),
    ) -> int:
        """List resources."""
        cli: CliContext = ctx.obj
        apply_format(cli, output_format)
        client = cli.client()
        scope = resolve_scope(client, group=group, zone=zone)
        filters: dict[str, Any] = {"zone_id": scope.zone_id, "group_id": scope.group_id}
        if name is not None:
            filters["name"] = name
        models = spec.service(client).list_all(
            **{k: v for k, v in filters.items() if v is not None}
        )
        if cli.fmt == "json":
            items = [output.dump_item(m, spec.exclude) for m in models]
            output.emit_json(output.list_document(spec.name, items))
        else:
            output.emit_table(spec.columns, models)
        return EXIT_OK

    @sub.command("describe")
    def describe(
        ctx: typer.Context,
        target: str = typer.Argument(..., metavar="ID_OR_NAME", help="Numeric ID or exact name."),
        group: str | None = typer.Option(None, "--group", help="Group name or ID."),  # noqa: UP007
        zone: str | None = typer.Option(None, "--zone", help="Zone name or ID."),  # noqa: UP007
        output_format: str | None = typer.Option(  # noqa: UP007
            None, "-o", "--output", help="Output format: json or table."
        ),
    ) -> int:
        """Describe one resource by numeric ID or exact name."""
        cli: CliContext = ctx.obj
        apply_format(cli, output_format)
        client = cli.client()
        service = spec.service(client)
        if is_id(target):
            model = service.get(int(target))
        else:
            scope = resolve_scope(client, group=group, zone=zone)
            try:
                model = service.get_by_name(target, zone_id=scope.zone_id, group_id=scope.group_id)
            except AmbiguousLookupError as exc:
                raise AmbiguousNameError(str(exc)) from exc
        if cli.fmt == "json":
            output.emit_json(
                output.describe_document(spec.name, output.dump_item(model, spec.exclude))
            )
        else:
            output.emit_table(spec.columns, [model])
        return EXIT_OK

    return sub
