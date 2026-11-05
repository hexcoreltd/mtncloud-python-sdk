"""Read-only instance placement resolution for CLI and CI consumers."""

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, Any

import typer
from pydantic import BaseModel, ConfigDict, Field
from pydantic import ValidationError as PydanticValidationError

from mtn_cloud.cli import output
from mtn_cloud.cli.errors import EXIT_OK, AmbiguousNameError
from mtn_cloud.cli.registry import Column
from mtn_cloud.cli.scope import is_id
from mtn_cloud.modern_exceptions import AmbiguousLookupError, MtnCloudError

if TYPE_CHECKING:
    from mtn_cloud.cli.app import CliContext, CliState


class _ResolvedSelection(BaseModel):
    """Only known scalar selections may leave the resolver through CLI output."""

    model_config = ConfigDict(strict=True, hide_input_in_errors=True)

    name: str = Field(min_length=1)
    cloud: str = Field(min_length=1)
    group_id: int = Field(gt=0)
    zone_id: int = Field(gt=0)
    type: str = Field(min_length=1)
    layout: int = Field(gt=0)
    plan: int = Field(gt=0)
    resource_pool_id: str = Field(min_length=1)


def _text(value: str, option: str) -> str:
    value = value.strip()
    if not value:
        raise typer.BadParameter("must not be empty", param_hint=option)
    return value


def _selector(value: str | None, option: str) -> str | int | None:
    if value is None:
        return None
    value = _text(value, option)
    if is_id(value) or (value.startswith("-") and is_id(value[1:])):
        numeric = int(value)
        if numeric <= 0:
            raise typer.BadParameter("IDs must be positive integers", param_hint=option)
        return numeric
    return value


def register_plan(app: typer.Typer, state: CliState) -> None:
    """Register a command with no apply path or resource-changing options."""

    @app.command()
    def plan(
        ctx: typer.Context,
        name: str = typer.Option(..., "--name", help="Instance name."),
        type_code: str = typer.Option(..., "--type-code", help="Instance type code."),
        group: str = typer.Option(..., "--group", help="Group name or positive ID."),
        service_plan: str = typer.Option(..., "--plan", help="Service plan name, code or ID."),
        zone: str | None = typer.Option(  # noqa: UP007
            None, "--zone", help="Zone name or positive ID; otherwise use the SDK default."
        ),
        resource_pool: str | None = typer.Option(  # noqa: UP007
            None, "--resource-pool", help="Resource pool name, code or positive ID."
        ),
        layout: str | None = typer.Option(  # noqa: UP007
            None, "--layout", help="Layout name or positive ID; otherwise use the SDK default."
        ),
        network_id: int | None = typer.Option(  # noqa: UP007
            None, "--network-id", min=1, help="Private network ID to check against placement."
        ),
        external_network_id: str | None = typer.Option(  # noqa: UP007
            None, "--external-network-id", help="External network reference (not validated)."
        ),
        root_volume_size_gb: int = typer.Option(
            10, "--root-volume-size-gb", min=1, help="Requested root volume size in GiB."
        ),
        security_group: str = typer.Option(
            "default", "--security-group", help="Requested security group name (not validated)."
        ),
        create_user: bool = typer.Option(
            True,
            "--create-user/--no-create-user",
            help="Request user creation during provisioning.",
        ),
        output_format: str | None = typer.Option(  # noqa: UP007
            None, "-o", "--output", help="Output format: json or table."
        ),
    ) -> int:
        """Resolve instance placement without creating resources."""
        # Reuse format validation without a module import cycle.
        from mtn_cloud.cli.app import _validate_format

        cli: CliContext = ctx.obj
        if output_format is not None:
            cli.fmt = _validate_format(output_format)
            state.fmt = cli.fmt
        name = _text(name, "--name")
        if len(name) > 255:
            raise typer.BadParameter("must be at most 255 characters", param_hint="--name")
        type_code = _text(type_code, "--type-code")
        group_selection = _selector(group, "--group")
        plan_selection = _selector(service_plan, "--plan")
        assert group_selection is not None and plan_selection is not None
        zone_selection = _selector(zone, "--zone")
        pool_selection = _selector(resource_pool, "--resource-pool")
        layout_selection = _selector(layout, "--layout")
        security_group = _text(security_group, "--security-group")
        if external_network_id is not None:
            external_network_id = _text(external_network_id, "--external-network-id")

        with cli.client() as client:
            try:
                result = client.instances.provision(
                    name,
                    type_code=type_code,
                    group=group_selection,
                    plan=plan_selection,
                    zone=zone_selection,
                    resource_pool=pool_selection,
                    layout=layout_selection,
                    network_id=network_id,
                    external_network_id=external_network_id,
                    root_volume_size_gb=root_volume_size_gb,
                    security_group=security_group,
                    create_user=create_user,
                    dry_run=True,
                    wait=False,
                )
            except AmbiguousLookupError as exc:
                raise AmbiguousNameError(
                    "Provisioning selection is ambiguous; choose explicit resource IDs."
                ) from exc
            except MtnCloudError as exc:
                safe = copy(exc)
                safe.message = (
                    "Provisioning discovery failed; check API access and selected resources."
                )
                safe.args = (safe.message,)
                safe.response = None
                raise safe from exc
            except PydanticValidationError as exc:
                raise RuntimeError("Invalid provisioning discovery response") from exc
            except ValueError as exc:
                raise typer.BadParameter(
                    "Could not resolve provisioning inputs; check placement selections, "
                    "network compatibility and root volume size."
                ) from exc

        if not isinstance(result, dict):
            raise RuntimeError("Invalid provisioning dry-run result")
        resolved = _ResolvedSelection.model_validate(result).model_dump(mode="json")
        options = {
            "network_id": network_id,
            "external_network_id": external_network_id,
            "root_volume_size_gb": root_volume_size_gb,
            "security_group": security_group,
            "create_user": create_user,
        }
        document: dict[str, Any] = {
            "schema": "mtncloud.plan/v1",
            "resource": "instances",
            "dry_run": True,
            "resolved": resolved,
            "options": options,
        }
        if cli.fmt == "json":
            output.emit_json(document)
        else:
            columns = (Column("Field", lambda row: row[0]), Column("Value", lambda row: row[1]))
            output.emit_table(columns, [("dry_run", True), *resolved.items(), *options.items()])
        return EXIT_OK
