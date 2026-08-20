# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017, 2023 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Python wrapper for autocorrectinfofile shell script."""

import subprocess
import sys
from pathlib import Path


def main():
    """Execute the autocorrectinfofile shell script with all arguments passed through."""
    # Try multiple locations for the shell script
    script_name = "autocorrectinfofile"

    # Location 1: Development - relative to this module (source tree)
    dev_location = Path(__file__).parent.parent.parent / "shell" / script_name

    # Location 2: Installed - in sys.prefix/share/lftools-uv/shell/
    installed_location = Path(sys.prefix) / "share" / "lftools-uv" / "shell" / script_name

    # Location 3: Virtual environment or user install - check both prefix and base_prefix
    venv_location = Path(sys.base_prefix) / "share" / "lftools-uv" / "shell" / script_name

    # Try locations in order
    shell_script = None
    for location in [dev_location, installed_location, venv_location]:
        if location.exists():
            shell_script = location
            break

    if shell_script is None:
        print("Error: Shell script not found at any of the following locations:", file=sys.stderr)
        print(f"  - {dev_location}", file=sys.stderr)
        print(f"  - {installed_location}", file=sys.stderr)
        print(f"  - {venv_location}", file=sys.stderr)
        sys.exit(1)

    cmd = [str(shell_script)] + sys.argv[1:]
    try:
        result = subprocess.run(cmd, check=False)
        sys.exit(result.returncode)
    except FileNotFoundError:
        print(f"Error: Could not execute shell script at {shell_script}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
