# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017, 2023 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Print INFO.yaml committer entries for the members of an LFX committee."""

import logging
import sys

from lftools_uv.api.endpoints.lfx import LfxError
from lftools_uv.ldap_cli import helper_yaml4info
from lftools_uv.typer_apps.lfx.committee import MEMBERS_FORBIDDEN_HINT, handle_lfx_error

USAGE = """\
Usage:

yaml4info sso-group-name

prints INFO.yaml committer entries for the members of the LFX committee
whose SSO group name is sso-group-name, one committee per call. It needs
an LFX token with the auditor relation on the committee, taken as
'lftools-uv lfx' takes it.
Example: yaml4info 'opnfv-gerrit-releng-committers'
"""


def main() -> int:
    """Print the committers of the committee named on the command line, and return the exit status."""
    args = sys.argv[1:]
    if not args:
        sys.stdout.write(USAGE)
        return 1
    if args[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0
    if args[0].startswith("-"):
        print(f"Unknown option: {args[0]}", file=sys.stderr)
        return 1
    if len(args) > 1:
        print("Error: yaml4info takes one SSO group name", file=sys.stderr)
        return 1

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        committers = helper_yaml4info(args[0])
    except LfxError as exc:
        status: int = handle_lfx_error(exc, MEMBERS_FORBIDDEN_HINT).exit_code
        return status
    except KeyboardInterrupt:
        return 130
    sys.stdout.write(committers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
