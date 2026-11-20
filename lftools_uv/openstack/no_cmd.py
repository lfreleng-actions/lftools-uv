# -*- code: utf-8 -*-
# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""CLI configuration for openstack command."""

__author__ = "Thanh Ha"


import click


@click.group()
@click.pass_context
def openstack(ctx, os_cloud):
    """Provides an OpenStack interface (unavailable).

    The OpenStack modules failed to import, so this interface is disabled.
    Reinstall lftools-uv to restore its core dependencies.
    """
    pass
