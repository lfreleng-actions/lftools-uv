# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the bundled shell scripts' calls back into the CLI.

lftools-uv installs only the ``lftools-uv`` executable, so a script calling
``lftools`` fails, or silently runs a legacy install instead. The ``ldap``
group and the working ``infofile`` commands exist only in the Click front-end,
so those calls also need ``LEGACY_CLI=1``. On the default Typer CLI,
``infofile get-committers`` is a stub that exits 0, and ``autocorrectinfofile``
would then diff two identical stub outputs and report no discrepancy.

Each script runs under real bash, with a PATH holding only stubs and system
directories. The ``lftools-uv`` stub records every call along with the
``LEGACY_CLI`` value it saw. A ``lftools`` stub records any call to the legacy
binary, and network tools are stubbed so nothing leaves the machine.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SHELL_DIR = Path(__file__).resolve().parent.parent / "shell"
BASH = shutil.which("bash") or "/bin/bash"

LFTOOLS_UV_STUB = """#!/bin/sh
printf '%s|%s\\n' "${LEGACY_CLI-}" "$*" >> "$CALL_LOG"
for last; do :; done
case "$1 $2" in
  "ldap csv") echo "grp,alice,Alice Example,alice@example.org" ;;
  "ldap yaml4info") echo "    - name: 'Bob Example'" ;;
  "infofile get-committers")
    case "$last" in
      *LDAP.yaml) echo "id: bob" ;;
      *) echo "id: alice" ;;
    esac ;;
  "lfidapi search-members") echo "alice <alice@example.org>" ;;
esac
exit 0
"""

LEGACY_TRAP_STUB = """#!/bin/sh
printf 'LEGACY-BINARY|%s\\n' "$*" >> "$CALL_LOG"
exit 127
"""

SSH_STUB = """#!/bin/sh
case "$*" in
  *set-project*) exit 1 ;;
  *"gerrit version"*) echo "gerrit version 3.10" ;;
esac
exit 0
"""

SILENT_FAILURE_STUB = "#!/bin/sh\nexit 1\n"


@pytest.fixture
def sandbox(tmp_path: Path) -> dict[str, str]:
    """Environment whose PATH resolves CLI and network tools to stubs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {
        "lftools-uv": LFTOOLS_UV_STUB,
        "lftools": LEGACY_TRAP_STUB,
        "ssh": SSH_STUB,
        "curl": SILENT_FAILURE_STUB,
        "git": SILENT_FAILURE_STUB,
    }
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)

    call_log = tmp_path / "calls.log"
    call_log.touch()
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "CALL_LOG": str(call_log),
    }


def _run(script: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [BASH, str(SHELL_DIR / script), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )


def _calls(env: dict[str, str]) -> list[str]:
    return Path(env["CALL_LOG"]).read_text().splitlines()


@pytest.mark.xfail(strict=True, reason="yaml4info calls lftools")
def test_yaml4info_reads_ldap_through_legacy_cli(sandbox):
    """``ldap csv`` exists only in the Click front-end."""
    result = _run("yaml4info", ["grp"], sandbox)

    assert _calls(sandbox) == ["1|ldap csv grp"]
    assert "- name: 'Alice Example'" in result.stdout


@pytest.mark.xfail(strict=True, reason="inactivecommitters calls lftools")
def test_inactivecommitters_reads_ldap_through_legacy_cli(sandbox):
    """``ldap csv`` exists only in the Click front-end."""
    _run("inactivecommitters", ["gerrit.example.org/gerrit", "grp"], sandbox)

    assert _calls(sandbox) == ["1|ldap csv grp"]


@pytest.mark.xfail(strict=True, reason="autocorrectinfofile calls lftools")
def test_autocorrectinfofile_uses_legacy_cli_throughout(sandbox, tmp_path):
    """Every call reaches a real Click command, not a Typer stub.

    The two ``get-committers`` reads run concurrently in process
    substitutions, so the comparison ignores call order.
    """
    work = tmp_path / "work"
    (work / "repo").mkdir(parents=True)
    (work / "repo" / "INFO.yaml").write_text("committers: []\n")
    env = {**sandbox, "DIR": str(work)}

    _run("autocorrectinfofile", ["https://gerrit.example.org/r", "grp", "repo"], env)

    info, ldap = f"{work}/repo/INFO.yaml", f"{work}/LDAP.yaml"
    assert sorted(_calls(env)) == sorted(
        [
            "1|ldap yaml4info grp",
            f"1|infofile get-committers {ldap}",
            f"1|infofile get-committers {info}",
            f"1|infofile get-committers --id alice {info}",
            f"1|infofile sync-committers {info} {ldap} bob --repo repo",
        ]
    )


@pytest.mark.xfail(strict=True, reason="gerrit_create calls lftools")
def test_gerrit_create_checks_ldap_group_with_lftools_uv(sandbox, tmp_path):
    """``lfidapi search-members`` works in the default Typer front-end."""
    args = ["-s", "gerrit.example.org", "-o", "grp", "-r", "foo/bar", "-u", "bot", "-w", str(tmp_path / "ws")]

    _run("gerrit_create", args, sandbox)

    assert "|lfidapi search-members grp" in _calls(sandbox)


@pytest.mark.xfail(strict=True, reason="usage text names lftools")
@pytest.mark.parametrize("script", ["yaml4info", "autocorrectinfofile"])
def test_usage_names_lftools_uv(sandbox, script):
    """Usage text points at the command that is installed.

    Usage echoes ``$0``, so the script's own path is removed first; the
    checkout directory name must not decide the result.
    """
    result = _run(script, [], sandbox)
    text = (result.stdout + result.stderr).replace(str(SHELL_DIR), "")

    assert re.search(r"\blftools(?!-uv)\b", text) is None
    assert "lftools-uv ldap" in text


def test_sandbox_resolves_cli_to_stub(sandbox):
    """Guard the fixture: the CLI resolves to the stub, never a real install."""
    found = shutil.which("lftools-uv", path=sandbox["PATH"])
    assert found is not None
    assert os.path.dirname(found) == sandbox["PATH"].split(":")[0]
