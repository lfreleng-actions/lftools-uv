# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Helper for INFO file generation."""

from subprocess import check_output


def helper_yaml4info(group: str) -> str:
    """Build yaml of committers for your INFO.yaml.

    The script's error output goes to stderr, never into the YAML.

    Raises:
        subprocess.CalledProcessError: If the LDAP lookup fails.
    """
    command = ["yaml4info", group]
    return check_output(command, text=True)
