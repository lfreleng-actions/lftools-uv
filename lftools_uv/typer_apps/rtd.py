# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer implementation of the Read the Docs commands.

Every command accepts ``--json`` and emits a machine-readable payload on
stdout when asked. Human-oriented output renders as a table. Errors and
warnings go to stderr so that a caller parsing stdout never has its
stream corrupted by a diagnostic.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import typer
from tabulate import tabulate

from lftools_uv.api.endpoints.readthedocs import (
    ReadTheDocs,
    ReadTheDocsError,
    version_slug,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

log = logging.getLogger(__name__)

rtd_app = typer.Typer(
    name="rtd",
    help="Read the Docs interface.",
    add_completion=False,
    no_args_is_help=True,
)


def emit_error(message: str) -> None:
    """Write an error message to stderr.

    Centralizes the format so that every Read the Docs command presents
    errors identically. Does NOT exit; the caller decides whether to
    raise ``typer.Exit``.
    """
    typer.echo(f"Error: {message}", err=True)


def handle_rtd_error(exc: ReadTheDocsError) -> typer.Exit:
    """Format a :class:`ReadTheDocsError` and return ``typer.Exit``.

    Callers should ``raise`` the returned ``typer.Exit`` to abort.
    """
    emit_error(str(exc))
    return typer.Exit(code=1)


def emit_table(rows: Sequence[Sequence[Any]], headers: Sequence[str]) -> None:
    """Print a human-readable table to stdout using ``tabulate``."""
    typer.echo(tabulate(list(rows), headers=list(headers)))


def emit_json(payload: Any) -> None:
    """Print a JSON payload to stdout with indent=2."""
    typer.echo(json.dumps(payload, indent=2, sort_keys=False, default=str))


def _wants_json(ctx: typer.Context, json_output: bool) -> bool:
    """Resolve the effective ``--json`` setting.

    The flag is accepted both on the group callback and on each command,
    so a user may write either ``rtd --json project-list`` or
    ``rtd project-list --json``.
    """
    if json_output:
        return True
    options: dict[str, Any] = ctx.obj or {}
    return options.get("json_output") is True


def _client() -> ReadTheDocs:
    """Build an API client."""
    return ReadTheDocs()


def _json_option() -> Any:
    """Build the per-command ``--json`` option.

    Returns ``Any`` because ``typer.Option`` yields an ``OptionInfo``
    sentinel that Typer replaces with a ``bool`` at call time.
    """
    return typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
    )


@rtd_app.callback()
def rtd_callback(
    ctx: typer.Context,
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
    ),
) -> None:
    """Read the Docs interface."""
    ctx.obj = {
        **(ctx.obj or {}),
        "json_output": json_output,
    }


@rtd_app.command("project-list")
def project_list(
    ctx: typer.Context,
    json_output: bool = _json_option(),
) -> None:
    """Get a list of Read the Docs projects.

    Returns projects by their slug name, not their pretty name, since
    the slug is what other commands accept.

    Examples:
        lftools-uv rtd project-list
        lftools-uv rtd project-list --json
    """
    try:
        projects = _client().project_list()
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json({"projects": projects})
        return

    if not projects:
        typer.echo("No projects found")
        return
    emit_table([[p] for p in projects], ["Project Slug"])


@rtd_app.command("project-details")
def project_details(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Project slug name"),
    json_output: bool = _json_option(),
) -> None:
    """Get details for a specific Read the Docs project.

    Examples:
        lftools-uv rtd project-details onap-cps
        lftools-uv rtd project-details onap-cps --json
    """
    try:
        details = _client().project_details(project_slug)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(details)
        return

    rows = [
        ["Name", details.get("name", "")],
        ["Slug", details.get("slug", "")],
        ["Language", details.get("language", "")],
        ["Programming Language", details.get("programming_language", "")],
        ["Default Version", details.get("default_version", "")],
        ["Homepage", details.get("homepage", "")],
    ]
    emit_table(rows, ["Field", "Value"])


@rtd_app.command("project-create")
def project_create(
    ctx: typer.Context,
    project_name: str = typer.Argument(..., help="Project name"),
    repository_url: str = typer.Argument(..., help="Repository URL"),
    repository_type: str = typer.Argument(..., help="Repository type: git, hg, bzr or svn"),
    homepage: str = typer.Argument(..., help="Project homepage URL"),
    programming_language: str = typer.Argument(..., help="Programming language abbreviation, e.g. py"),
    language: str = typer.Argument(..., help="Two-letter language code, e.g. en"),
    json_output: bool = _json_option(),
) -> None:
    """Create a new Read the Docs project.

    Examples:
        lftools-uv rtd project-create onap-cps https://example.org/cps git https://onap-cps.readthedocs.io py en
    """
    try:
        result = _client().project_create(
            project_name,
            repository_url,
            repository_type,
            homepage,
            programming_language,
            language,
        )
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(result)
        return
    typer.echo(f"Created project '{project_name}'")


@rtd_app.command(
    "project-update",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
def project_update(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Project slug name"),
    json_output: bool = _json_option(),
) -> None:
    """Update an existing Read the Docs project.

    Accepts any number of ``key=value`` pairs matching the fields the
    Read the Docs API allows.

    Examples:
        lftools-uv rtd project-update onap-cps default_version=latest
    """
    updates: dict[str, str] = {}
    for item in ctx.args:
        if "=" not in item:
            emit_error(f"Expected key=value, received {item!r}")
            raise typer.Exit(code=1)
        key, value = item.split("=", 1)
        updates[key] = value

    if not updates:
        emit_error("No update parameters provided")
        raise typer.Exit(code=1)

    try:
        result = _client().project_update(project_slug, updates)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(result)
        return
    typer.echo(f"Updated project '{project_slug}'")


@rtd_app.command("project-version-list")
def project_version_list(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Project slug name"),
    json_output: bool = _json_option(),
) -> None:
    """Retrieve the active versions of a project.

    Examples:
        lftools-uv rtd project-version-list onap-cps
    """
    try:
        versions = _client().project_version_list(project_slug)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json({"project": project_slug, "versions": versions})
        return

    if not versions:
        typer.echo("No active versions found")
        return
    emit_table([[v] for v in versions], ["Version Slug"])


@rtd_app.command("project-version-details")
def project_version_details(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Project slug name"),
    version_slug_arg: str = typer.Argument(..., metavar="VERSION_SLUG", help="Version slug name"),
    from_branch: bool = typer.Option(
        False,
        "--from-branch",
        help="Treat VERSION_SLUG as a git branch name and slugify it first.",
    ),
    json_output: bool = _json_option(),
) -> None:
    """Retrieve details of a single version.

    Read the Docs addresses a version by its slug, so a branch named
    ``maintenance/3.7.10`` is stored as ``maintenance-3.7.10``. Pass
    ``--from-branch`` to convert a branch name automatically.

    Examples:
        lftools-uv rtd project-version-details onap-cps latest
        lftools-uv rtd project-version-details onap-cps maintenance/3.7.10 --from-branch
    """
    try:
        target = version_slug(version_slug_arg) if from_branch else version_slug_arg
        details = _client().project_version_details(project_slug, target)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(details)
        return

    rows = [
        ["Slug", details.get("slug", "")],
        ["Verbose Name", details.get("verbose_name", "")],
        ["Active", details.get("active", "")],
        ["Built", details.get("built", "")],
        ["Type", details.get("type", "")],
    ]
    emit_table(rows, ["Field", "Value"])


@rtd_app.command("project-version-update")
def project_version_update(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Project slug name"),
    version_slug_arg: str = typer.Argument(..., metavar="VERSION_SLUG", help="Version slug name"),
    active: bool = typer.Argument(..., help="Whether the version should be active"),
    from_branch: bool = typer.Option(
        False,
        "--from-branch",
        help="Treat VERSION_SLUG as a git branch name and slugify it first.",
    ),
    json_output: bool = _json_option(),
) -> None:
    """Update a version's active flag.

    Examples:
        lftools-uv rtd project-version-update onap-cps maintenance/3.7.10 true --from-branch
    """
    try:
        target = version_slug(version_slug_arg) if from_branch else version_slug_arg
        result = _client().project_version_update(project_slug, target, active)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(result)
        return
    state = "active" if active else "inactive"
    typer.echo(f"Marked version '{result['version']}' of '{project_slug}' as {state}")


@rtd_app.command("project-build-list")
def project_build_list(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Project slug name"),
    json_output: bool = _json_option(),
) -> None:
    """Retrieve a project's running builds.

    With ``--json`` the payload always carries a ``builds`` list, empty
    when nothing is running, so a caller can parse the result without a
    special case. Table output prints a short message instead.

    Examples:
        lftools-uv rtd project-build-list onap-cps --json
    """
    try:
        builds = _client().project_build_list(project_slug)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json({"project": project_slug, "count": len(builds), "builds": builds})
        return

    if not builds:
        typer.echo("There are no active builds.")
        return
    rows = [
        [
            b.get("id", ""),
            b.get("version", ""),
            b.get("state", ""),
            b.get("success", ""),
        ]
        for b in builds
    ]
    emit_table(rows, ["Build ID", "Version", "State", "Success"])


@rtd_app.command("project-build-details")
def project_build_details(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Project slug name"),
    build_id: str = typer.Argument(..., help="Build identifier"),
    json_output: bool = _json_option(),
) -> None:
    """Retrieve the details of a specific build.

    Examples:
        lftools-uv rtd project-build-details onap-cps 9584913 --json
    """
    try:
        details = _client().project_build_details(project_slug, build_id)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(details)
        return

    rows = [
        ["ID", details.get("id", "")],
        ["Version", details.get("version", "")],
        ["State", details.get("state", "")],
        ["Success", details.get("success", "")],
        ["Duration", details.get("duration", "")],
    ]
    emit_table(rows, ["Field", "Value"])


@rtd_app.command("project-build-trigger")
def project_build_trigger(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Project slug name"),
    version_slug_arg: str = typer.Argument(..., metavar="VERSION_SLUG", help="Version slug to build"),
    from_branch: bool = typer.Option(
        False,
        "--from-branch",
        help="Treat VERSION_SLUG as a git branch name and slugify it first.",
    ),
    json_output: bool = _json_option(),
) -> None:
    """Trigger a build of a project version.

    Examples:
        lftools-uv rtd project-build-trigger onap-cps latest
        lftools-uv rtd project-build-trigger onap-cps maintenance/3.7.10 --from-branch
    """
    try:
        target = version_slug(version_slug_arg) if from_branch else version_slug_arg
        result = _client().project_build_trigger(project_slug, target)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(result)
        return

    build = result.get("build")
    build_id = build.get("id", "") if isinstance(build, dict) else ""
    typer.echo(f"Triggered build {build_id} for '{project_slug}'")


@rtd_app.command("subproject-list")
def subproject_list(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Parent project slug name"),
    json_output: bool = _json_option(),
) -> None:
    """Get a list of subprojects for a project.

    Examples:
        lftools-uv rtd subproject-list onap
    """
    try:
        subprojects = _client().subproject_list(project_slug)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json({"project": project_slug, "subprojects": subprojects})
        return

    if not subprojects:
        typer.echo("No subprojects found")
        return
    emit_table([[s] for s in subprojects], ["Subproject Slug"])


@rtd_app.command("subproject-details")
def subproject_details(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Parent project slug name"),
    subproject_slug: str = typer.Argument(..., help="Subproject slug name"),
    json_output: bool = _json_option(),
) -> None:
    """Retrieve the details of a specific subproject.

    Examples:
        lftools-uv rtd subproject-details onap onap-cps --json
    """
    try:
        details = _client().subproject_details(project_slug, subproject_slug)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(details)
        return

    child = details.get("child")
    child_slug = child.get("slug", "") if isinstance(child, dict) else ""
    rows = [
        ["Parent", project_slug],
        ["Child", child_slug],
        ["Alias", details.get("alias", "")],
    ]
    emit_table(rows, ["Field", "Value"])


@rtd_app.command("subproject-create")
def subproject_create(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Parent project slug name"),
    subproject_slug: str = typer.Argument(..., help="Subproject slug name"),
    alias: str | None = typer.Option(None, "--alias", help="Optional user-defined alias"),
    json_output: bool = _json_option(),
) -> None:
    """Create a project/subproject relationship.

    Examples:
        lftools-uv rtd subproject-create onap onap-cps
    """
    try:
        result = _client().subproject_create(project_slug, subproject_slug, alias)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(result)
        return
    typer.echo(f"Created the {project_slug} {subproject_slug} relationship")


@rtd_app.command("subproject-delete")
def subproject_delete(
    ctx: typer.Context,
    project_slug: str = typer.Argument(..., help="Parent project slug name"),
    subproject_slug: str = typer.Argument(..., help="Subproject slug name"),
    json_output: bool = _json_option(),
) -> None:
    """Delete a project/subproject relationship.

    Examples:
        lftools-uv rtd subproject-delete onap onap-cps
    """
    try:
        result = _client().subproject_delete(project_slug, subproject_slug)
    except ReadTheDocsError as exc:
        raise handle_rtd_error(exc) from exc

    if _wants_json(ctx, json_output):
        emit_json(result)
        return
    typer.echo(f"Removed the {project_slug} {subproject_slug} relationship")


def get_rtd_app() -> typer.Typer:
    """Get the rtd Typer app instance.

    This function is used by other modules to register the rtd commands.
    """
    return rtd_app
