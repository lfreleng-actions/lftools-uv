# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the exit status and requests of the ``shell/deploy`` script.

The ``deploy`` console script runs ``shell/deploy``, and so does Click's
``sign deploy-nexus``, through ``deploy nexus-stage``. A failed upload,
download or Nexus request must fail the command, and a request must carry
the fields Nexus expects.

Each test runs the script under real bash, with a PATH holding only stubs and
links to the system tools the script calls. The ``curl`` and ``wget`` stubs
record their arguments and answer from a plan, so nothing leaves the machine.
"""

import functools
import gzip
import json
import shutil
import subprocess
import sys
import zipfile
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "shell" / "deploy"
BASH = shutil.which("bash") or "/bin/bash"
NEXUS = "http://nexus.invalid"
BUILD_URL = "http://jenkins.invalid/job/app/1/"
STAGED = "<promoteResponse><data><stagedRepositoryId>x-1001</stagedRepositoryId></data></promoteResponse>"
NEXUS_ERROR = "<nexus-error><errors><error><id>*</id><msg>boom</msg></error></errors></nexus-error>"

# The system tools the script calls, linked into the sandbox so that its PATH
# holds nothing else. GNU parallel is linked only where a test asks for it.
TOOLS = (
    "awk",
    "basename",
    "cat",
    "cut",
    "dirname",
    "du",
    "echo",
    "env",
    "file",
    "find",
    "grep",
    "gzip",
    "head",
    "ls",
    "mkdir",
    "mv",
    "nproc",
    "perl",
    "ps",
    "rm",
    "sed",
    "sh",
    "sort",
    "tee",
    "touch",
    "true",
    "unzip",
    "xargs",
    "zip",
)

# Records its arguments, then answers as the first rule in $CURL_PLAN whose
# "match" is in the URL says: an HTTP "code" and "body", and a curl "exit"
# status for a transfer that failed. A failed transfer reports code 000
# unless its rule gives one, as when a response is cut short. It copies each
# uploaded file to $UPLOADS.
CURL_STUB = r"""
import json
import os
import shutil
import sys

args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps({"tool": "curl", "args": args}) + "\n")


def option(name):
    if name in args[:-1]:
        return args[args.index(name) + 1]
    return None


url = args[-1]
rule = next((rule for rule in json.loads(os.environ["CURL_PLAN"]) if rule["match"] in url), {})
status = rule.get("exit", 0)
upload = option("--upload-file")
if upload is not None and not status:
    if os.path.isfile(upload):
        shutil.copy(upload, os.path.join(os.environ["UPLOADS"], os.path.basename(upload)))
    else:
        status = 26
code = rule.get("code", 0 if status else 201)
body = rule.get("body", "")
if status:
    print(f"curl: ({status}) the stub failed the transfer", file=sys.stderr)
written = (option("-w") or "").replace("\\n", "\n").replace("%{http_code}", f"{code:03d}")
sys.stdout.write(body + written)
sys.exit(status)
"""

# Records its arguments, then saves a console log to the -O file, or exits
# with the "exit" status of the first rule in $WGET_PLAN whose "match" is in
# the URL, leaving the file empty as wget does.
WGET_STUB = r"""
import json
import os
import sys

args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps({"tool": "wget", "args": args}) + "\n")
url = args[-1]
status = next((rule["exit"] for rule in json.loads(os.environ["WGET_PLAN"]) if rule["match"] in url), 0)
with open(args[args.index("-O") + 1], "w") as output:
    if not status:
        output.write(f"Console of {url}\n-----END_OF_BUILD-----\nAfter the build\n")
if status:
    print(f"wget: the stub failed with exit status {status}", file=sys.stderr)
sys.exit(status)
"""


# Runs the system mktemp, at $REAL_MKTEMP, and records each path it creates.
MKTEMP_STUB = r"""
import json
import os
import subprocess
import sys

made = subprocess.run([os.environ["REAL_MKTEMP"], *sys.argv[1:]], capture_output=True, text=True, check=False)
if made.returncode == 0:
    with open(os.environ["CALL_LOG"], "a") as log:
        log.write(json.dumps({"tool": "mktemp", "args": [made.stdout.strip()]}) + "\n")
sys.stdout.write(made.stdout)
sys.stderr.write(made.stderr)
sys.exit(made.returncode)
"""


@pytest.fixture
def sandbox(tmp_path):
    """Return the environment to run the script in: stubs and system tools, but no GNU parallel."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool, path="/usr/bin:/bin")
        if found:
            (bin_dir / tool).symlink_to(found)
    for name, source in (("curl", CURL_STUB), ("wget", WGET_STUB), ("mktemp", MKTEMP_STUB)):
        stub = bin_dir / name
        stub.write_text(f"#!{sys.executable}{source}")
        stub.chmod(0o755)
    (tmp_path / "uploads").mkdir()
    return {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "REAL_MKTEMP": shutil.which("mktemp", path="/usr/bin:/bin") or "mktemp",
        "SHELL": BASH,
        "CALL_LOG": str(tmp_path / "calls.log"),
        "UPLOADS": str(tmp_path / "uploads"),
        "CURL_PLAN": "[]",
        "WGET_PLAN": "[]",
    }


@pytest.fixture
def m2repo(tmp_path):
    """Return a Maven repository holding a jar and its pom, and files ``deploy nexus`` skips."""
    root = tmp_path / "m2repo"
    version = root / "org" / "example" / "app" / "1.0"
    version.mkdir(parents=True)
    (version / "app-1.0.jar").write_bytes(b"jar")
    (version / "app-1.0.pom").write_text("<project/>")
    (version / "_remote.repositories").write_text("")
    (version.parent / "maven-metadata.xml").write_text("<metadata/>")
    return root


@pytest.fixture
def workspace(tmp_path):
    """Return a workspace whose archives directory holds a log."""
    root = tmp_path / "workspace"
    (root / "archives").mkdir(parents=True)
    (root / "archives" / "build.log").write_text("Built\n")
    return root


@functools.cache
def _gnu_parallel() -> str | None:
    """Return the path of GNU parallel, or None if it is not installed."""
    path = shutil.which("parallel")
    if path is None:
        return None
    version = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60, check=False)
    return path if version.stdout.startswith("GNU parallel") else None


def _use_parallel(env: dict[str, str]) -> None:
    """Link GNU parallel into *env*'s PATH, so that ``deploy nexus`` uploads with it."""
    path = _gnu_parallel()
    if path is None:
        pytest.skip("GNU parallel is not installed")
    else:
        (Path(env["PATH"]) / "parallel").symlink_to(path)


def _plan(env: dict[str, str], tool: str, *rules: dict[str, Any]) -> None:
    """Make the *tool* stub answer as the first of *rules* whose ``match`` is in the URL says."""
    env[f"{tool.upper()}_PLAN"] = json.dumps(rules)


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``deploy`` with *args* in *env*, from its home directory."""
    return subprocess.run(
        [BASH, str(SCRIPT), *args], capture_output=True, text=True, env=env, cwd=env["HOME"], timeout=120, check=False
    )


def _calls(env: dict[str, str], tool: str) -> list[list[str]]:
    """Return the arguments of each call to the *tool* stub, in order."""
    log = Path(env["CALL_LOG"])
    entries = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return [entry["args"] for entry in entries if entry["tool"] == tool]


def _urls(env: dict[str, str], tool: str) -> list[str]:
    """Return the URL each call to the *tool* stub requested, in order."""
    return [args[-1] for args in _calls(env, tool)]


def _uploaded_log(env: dict[str, str], name: str) -> str:
    """Return the log *name*, gzipped in the console-logs.zip ``deploy logs`` uploaded."""
    with zipfile.ZipFile(Path(env["UPLOADS"]) / "console-logs.zip") as archive:
        return gzip.decompress(archive.read(name)).decode()


MODES = pytest.mark.parametrize("parallel", [True, False], ids=["parallel", "serial"])


@MODES
def test_nexus_uploads_every_file(sandbox: dict[str, str], m2repo: Path, parallel: bool) -> None:
    if parallel:
        _use_parallel(sandbox)

    result = _run(sandbox, "nexus", f"{NEXUS}/content/repositories/releases", str(m2repo))

    assert result.returncode == 0, result.stderr
    assert sorted(_urls(sandbox, "curl")) == [
        f"{NEXUS}/content/repositories/releases/org/example/app/1.0/app-1.0.{extension}" for extension in ("jar", "pom")
    ]


@pytest.mark.parametrize("parallel", [True, False], ids=["parallel", "serial"])
def test_nexus_failed_upload_exits_1(sandbox: dict[str, str], m2repo: Path, parallel: bool) -> None:
    if parallel:
        _use_parallel(sandbox)
    _plan(sandbox, "curl", {"match": "app-1.0.jar", "code": 500, "body": "Server Error"})

    result = _run(sandbox, "nexus", f"{NEXUS}/content/repositories/releases", str(m2repo))

    assert result.returncode == 1


@pytest.mark.parametrize(
    "failure", [{"code": 500, "body": "Server Error"}, {"code": 201, "exit": 18}], ids=["server-error", "cut-short"]
)
def test_nexus_failed_upload_reported_on_stderr(sandbox: dict[str, str], m2repo: Path, failure: dict[str, Any]) -> None:
    """A failed upload is reported on stderr, including one curl cuts short after Nexus answered."""
    _plan(sandbox, "curl", {"match": "app-1.0.jar", **failure})

    result = _run(sandbox, "nexus", f"{NEXUS}/content/repositories/releases", str(m2repo))

    assert result.returncode == 1
    assert "ERROR" in result.stderr


@pytest.mark.parametrize("parallel", [True, False], ids=["parallel", "serial"])
def test_nexus_stage_failed_upload_leaves_repo_open(sandbox: dict[str, str], m2repo: Path, parallel: bool) -> None:
    if parallel:
        _use_parallel(sandbox)
    _plan(sandbox, "curl", {"match": "/start", "body": STAGED}, {"match": "app-1.0.jar", "code": 500})

    result = _run(sandbox, "nexus-stage", NEXUS, "prof", str(m2repo))

    assert result.returncode == 1
    assert not [url for url in _urls(sandbox, "curl") if url.endswith("/finish")]
    assert "Completed uploading" not in result.stdout


@pytest.mark.parametrize(
    "answer",
    [{"code": 400, "body": NEXUS_ERROR}, {"code": 201, "body": "<promoteResponse><data/></promoteResponse>"}],
    ids=["nexus-error", "no-repository-id"],
)
def test_nexus_stage_create_failure_uploads_nothing(
    sandbox: dict[str, str], m2repo: Path, answer: dict[str, Any]
) -> None:
    _plan(sandbox, "curl", {"match": "/start", **answer})

    result = _run(sandbox, "nexus-stage", NEXUS, "prof", str(m2repo))

    assert result.returncode == 1
    assert _urls(sandbox, "curl") == [f"{NEXUS}/service/local/staging/profiles/prof/start"]
    assert "ERROR" in result.stderr
    assert "ERROR" not in result.stdout


def test_stage_repo_create_prints_repository_id(sandbox: dict[str, str]) -> None:
    _plan(sandbox, "curl", {"match": "/start", "body": STAGED})

    result = _run(sandbox, "nexus-stage-repo-create", NEXUS, "prof")

    assert result.returncode == 0, result.stderr
    assert result.stdout == "x-1001\n"


@pytest.fixture
def unpublished(tmp_path):
    """Return a Maven repository holding only maven-metadata.xml, which deploy nexus skips."""
    root = tmp_path / "unpublished"
    (root / "org" / "example").mkdir(parents=True)
    (root / "org" / "example" / "maven-metadata.xml").write_text("<metadata/>")
    return root


def test_nexus_nothing_to_deploy_exits_1(sandbox: dict[str, str], unpublished: Path) -> None:
    result = _run(sandbox, "nexus", f"{NEXUS}/content/repositories/releases", str(unpublished))

    assert result.returncode == 1
    assert _urls(sandbox, "curl") == []
    assert "Nothing to deploy" in result.stderr


def test_nexus_allow_empty_deploys_nothing(sandbox: dict[str, str], unpublished: Path) -> None:
    result = _run(sandbox, "nexus", "-a", f"{NEXUS}/content/repositories/releases", str(unpublished))

    assert result.returncode == 0, result.stderr
    assert _urls(sandbox, "curl") == []


@pytest.mark.parametrize("missing", [False, True], ids=["empty", "missing"])
def test_nexus_stage_nothing_to_deploy_creates_no_repository(
    sandbox: dict[str, str], unpublished: Path, missing: bool
) -> None:
    deploy_dir = unpublished / "missing" if missing else unpublished

    result = _run(sandbox, "nexus-stage", NEXUS, "prof", str(deploy_dir))

    assert result.returncode == 1
    assert _urls(sandbox, "curl") == []
    assert "Nothing to deploy" in result.stderr


@pytest.mark.parametrize("files", [False, True], ids=["empty", "with-files"])
def test_nexus_stage_allow_empty(sandbox: dict[str, str], unpublished: Path, m2repo: Path, files: bool) -> None:
    """-a stages an empty repository, and still uploads every file of a full one."""
    _plan(sandbox, "curl", {"match": "/start", "body": STAGED})

    result = _run(sandbox, "nexus-stage", "-a", NEXUS, "prof", str(m2repo if files else unpublished))

    assert result.returncode == 0, result.stderr
    urls = _urls(sandbox, "curl")
    staged = f"{NEXUS}/service/local/staging/deployByRepositoryId/x-1001/org/example/app/1.0"
    assert urls[0] == f"{NEXUS}/service/local/staging/profiles/prof/start"
    assert urls[-1] == f"{NEXUS}/service/local/staging/profiles/prof/finish"
    assert sorted(urls[1:-1]) == ([f"{staged}/app-1.0.{extension}" for extension in ("jar", "pom")] if files else [])


def _arguments(command: str, tmp_path: Path) -> list[str]:
    """Return arguments for *command*, creating the file it uploads."""
    if command == "nexus-stage-repo-create":
        return [NEXUS, "prof"]
    if command == "nexus-stage-repo-close":
        return [NEXUS, "prof", "x-1001"]
    if command == "file":
        jar = tmp_path / "app-1.0.jar"
        jar.write_bytes(b"jar")
        return [NEXUS, "releases", "org.example", "app", "1.0", "jar", str(jar)]
    site = tmp_path / "site.zip"
    with zipfile.ZipFile(site, "w") as archive:
        archive.writestr("index.html", "<html/>")
    return [NEXUS, "site", "org.example.app", str(site)]


# Each command that makes a single Nexus request, and part of its URL.
REQUESTS = pytest.mark.parametrize(
    ("command", "match"),
    [
        ("nexus-stage-repo-create", "/start"),
        ("nexus-stage-repo-close", "/finish"),
        ("file", "/artifact/maven/content"),
        ("nexus-zip", "/content-compressed/"),
    ],
)


@REQUESTS
def test_successful_request_exits_0(sandbox: dict[str, str], tmp_path: Path, command: str, match: str) -> None:
    _plan(sandbox, "curl", {"match": match, "body": STAGED})

    result = _run(sandbox, command, *_arguments(command, tmp_path))

    assert result.returncode == 0, result.stderr


@REQUESTS
@pytest.mark.parametrize(
    "failure",
    [{"exit": 7}, {"code": 404, "body": "Not Found"}, {"code": 201, "exit": 18, "body": STAGED}],
    ids=["unreachable", "not-found", "cut-short"],
)
def test_failed_request_exits_1(
    sandbox: dict[str, str], tmp_path: Path, command: str, match: str, failure: dict[str, Any]
) -> None:
    _plan(sandbox, "curl", {"match": match, **failure})

    result = _run(sandbox, command, *_arguments(command, tmp_path))

    assert result.returncode == 1
    assert "ERROR" in result.stderr


# An upload Nexus refuses, one that never reaches it, and one cut short after
# Nexus answered.
UPLOAD_FAILURES = pytest.mark.parametrize(
    "failure",
    [{"code": 500, "body": "Server Error"}, {"exit": 7}, {"code": 201, "exit": 18}],
    ids=["server-error", "unreachable", "cut-short"],
)


def test_archives_uploads_log_and_zip(sandbox: dict[str, str], workspace: Path) -> None:
    result = _run(sandbox, "archives", NEXUS, "silo/job/1", str(workspace))

    assert result.returncode == 0, result.stderr
    assert _urls(sandbox, "curl") == [
        f"{NEXUS}/content/repositories/logs/silo/job/1/archives.log.gz",
        f"{NEXUS}/service/local/repositories/logs/content-compressed/silo/job/1",
    ]


@UPLOAD_FAILURES
@pytest.mark.parametrize("match", ["archives.log.gz", "content-compressed"])
def test_archives_failed_upload_exits_1(
    sandbox: dict[str, str], workspace: Path, failure: dict[str, Any], match: str
) -> None:
    _plan(sandbox, "curl", {"match": match, **failure})

    result = _run(sandbox, "archives", NEXUS, "silo/job/1", str(workspace))

    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_logs_uploads_console_logs(sandbox: dict[str, str]) -> None:
    result = _run(sandbox, "logs", NEXUS, "silo/job/1", BUILD_URL)

    assert result.returncode == 0, result.stderr
    assert _urls(sandbox, "curl") == [f"{NEXUS}/service/local/repositories/logs/content-compressed/silo/job/1"]
    assert f"Console of {BUILD_URL}consoleText" in _uploaded_log(sandbox, "console.log.gz")


@UPLOAD_FAILURES
def test_logs_failed_upload_exits_1(sandbox: dict[str, str], failure: dict[str, Any]) -> None:
    _plan(sandbox, "curl", {"match": "content-compressed", **failure})

    result = _run(sandbox, "logs", NEXUS, "silo/job/1", BUILD_URL)

    assert result.returncode == 1
    assert "ERROR" in result.stderr


@pytest.mark.parametrize("match", ["consoleText", "timestamps"])
def test_logs_unreachable_jenkins_uploads_nothing(sandbox: dict[str, str], match: str) -> None:
    _plan(sandbox, "wget", {"match": match, "exit": 4})

    result = _run(sandbox, "logs", NEXUS, "silo/job/1", BUILD_URL)

    assert result.returncode == 1
    assert _urls(sandbox, "curl") == []


def _leftovers(env: dict[str, str]) -> list[str]:
    """Return each path the script created with mktemp that still exists."""
    return [path for [path] in _calls(env, "mktemp") if Path(path).exists()]


@pytest.mark.parametrize(
    ("command", "plan"),
    [
        ("logs", {"tool": "curl", "match": "content-compressed", "code": 500}),
        ("logs", {"tool": "wget", "match": "consoleText", "exit": 4}),
        ("archives", {"tool": "curl", "match": "archives.log.gz", "code": 500}),
    ],
    ids=["logs-upload", "logs-download", "archives-upload"],
)
def test_failed_transfer_removes_working_directory(
    sandbox: dict[str, str], workspace: Path, command: str, plan: dict[str, Any]
) -> None:
    """A failed transfer still removes the working directory, which holds the build environment dump."""
    tool = plan.pop("tool")
    _plan(sandbox, tool, plan)
    target = BUILD_URL if command == "logs" else str(workspace)

    result = _run(sandbox, command, NEXUS, "silo/job/1", target)

    assert result.returncode == 1
    assert _calls(sandbox, "mktemp")
    assert _leftovers(sandbox) == []


def test_successful_transfer_removes_working_directory(sandbox: dict[str, str], workspace: Path) -> None:
    assert _run(sandbox, "logs", NEXUS, "silo/job/1", BUILD_URL).returncode == 0
    assert _run(sandbox, "archives", NEXUS, "silo/job/1", str(workspace)).returncode == 0
    assert len(_calls(sandbox, "mktemp")) == 2
    assert _leftovers(sandbox) == []


def test_logs_http_error_leaves_placeholder(sandbox: dict[str, str]) -> None:
    """An HTTP error from Jenkins is not fatal: one without the Timestamper plugin answers 404."""
    _plan(sandbox, "wget", {"match": "timestamps", "exit": 8})

    result = _run(sandbox, "logs", NEXUS, "silo/job/1", BUILD_URL)

    assert result.returncode == 0, result.stderr
    placeholder = _uploaded_log(sandbox, "console-timestamp.log.gz")
    assert placeholder.startswith(f"Console log unavailable: {BUILD_URL}/timestamps")
    assert f"Console of {BUILD_URL}consoleText" in _uploaded_log(sandbox, "console.log.gz")


def _form(args: list[str]) -> list[tuple[str, str]]:
    """Return each multipart field option in curl's arguments *args*, with its value."""
    return [(flag, value) for flag, value in pairwise(args) if flag in ("-F", "--form", "--form-string")]


@pytest.mark.parametrize(("extra", "fields"), [([], []), (["sources"], ["c=sources"])], ids=["plain", "classifier"])
def test_file_sends_each_form_field(
    sandbox: dict[str, str], tmp_path: Path, extra: list[str], fields: list[str]
) -> None:
    jar = tmp_path / "app-1.0.jar"
    jar.write_bytes(b"jar")

    result = _run(sandbox, "file", NEXUS, "releases", "org.example", "app", "1.0", "jar", str(jar), *extra)

    assert result.returncode == 0, result.stderr
    [args] = _calls(sandbox, "curl")
    text = ["r=releases", "g=org.example", "a=app", "v=1.0", "p=jar", *fields]
    assert _form(args) == [*(("--form-string", field) for field in text), ("-F", f"file=@{jar}")]
