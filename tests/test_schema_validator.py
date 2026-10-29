# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the validator ``schema verify`` picks.

``schema verify`` must validate with the draft a schema names in
``$schema``, defaulting to Draft 4, and must exit 1 for a schema that
fails its own draft's meta-schema rather than let an invalid document
pass.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv import config
from lftools_uv.cli import cli
from lftools_uv.typer_apps.root import app

FIXTURES = Path(__file__).parent / "fixtures" / "schema"

MALFORMED_SCHEMA = """\
$schema: 'http://json-schema.org/schema#'
additionalProperties: 'false'
required: ['project']
properties:
  project:
    type: 'string'
"""

MALFORMED_DOCUMENT = """\
project: 'demo'
extra: 1
"""

CONST_PROPERTIES = """\
properties:
  kind:
    const: 'release'
  tags:
    type: array
    contains:
      const: 'stable'
"""

DRAFT7_SCHEMA = "$schema: 'http://json-schema.org/draft-07/schema#'\n" + CONST_PROPERTIES
UNVERSIONED_SCHEMA = "$schema: 'http://json-schema.org/schema#'\n" + CONST_PROPERTIES


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, args, obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


@pytest.fixture(autouse=True)
def no_user_config(tmp_path, monkeypatch):
    """Keep the root callbacks away from the user's own configuration."""
    monkeypatch.setattr(config, "LFTOOLS_CONFIG_FILE", str(tmp_path / "missing.ini"))


def _write(tmp_path: Path, name: str, text: str) -> str:
    path = tmp_path / name
    _ = path.write_text(text)
    return str(path)


@pytest.mark.xfail(strict=True, reason="#972: the schema itself is never checked")
@FRONT_ENDS
def test_malformed_schema_exits_1(run, tmp_path):
    """A schema that fails its meta-schema stops validation with exit 1."""
    schema = _write(tmp_path, "schema.yaml", MALFORMED_SCHEMA)
    document = _write(tmp_path, "doc.yaml", MALFORMED_DOCUMENT)

    result = run(["schema", "verify", document, schema])

    assert result.exit_code == 1


@pytest.mark.xfail(strict=True, reason="#972: every schema validates as Draft 4")
@FRONT_ENDS
def test_draft7_schema_uses_draft7(run, tmp_path):
    """A Draft 7 schema enforces ``const`` and ``contains``."""
    schema = _write(tmp_path, "schema.yaml", DRAFT7_SCHEMA)
    document = _write(tmp_path, "doc.yaml", "kind: 'snapshot'\ntags: ['beta']\n")

    result = run(["schema", "verify", document, schema])

    assert result.exit_code == 1


@FRONT_ENDS
def test_unversioned_schema_stays_draft4(run, tmp_path):
    """A schema naming no known draft still validates as Draft 4."""
    schema = _write(tmp_path, "schema.yaml", UNVERSIONED_SCHEMA)
    document = _write(tmp_path, "doc.yaml", "kind: 'snapshot'\n")

    result = run(["schema", "verify", document, schema])

    assert result.exit_code == 0


@FRONT_ENDS
@pytest.mark.parametrize(("document", "exit_code"), [("release.yaml", 0), ("release-broken.yaml", 1)])
def test_release_schema_unchanged(run, document, exit_code):
    """The release schema fixture validates as it did before."""
    result = run(["schema", "verify", str(FIXTURES / document), str(FIXTURES / "schema.yaml")])

    assert result.exit_code == exit_code
