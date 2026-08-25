.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

########
Commands
########

lftools-uv is a collection of scripts written directly in python or externally via
bash.

It supports the following commands:

.. toctree::
    :maxdepth: 2

    config
    deploy
    dco
    gerrit
    github
    infofile
    lfidapi
    license
    nexus
    nexus2
    nexus3
    openstack
    rtd
    schema
    sign
    version

Enable debugging via ``lftools-uv --debug`` preceding any commands or via
environment variable ``DEBUG=True``, this will print extra information if
available.

Output streams
==============

Every command splits what it writes across two streams.

**stdout** carries the result: the thing you asked for. Listings, tables,
``--json`` payloads, generated INFO.yaml documents, API tokens and the
staging repository id that ``deploy nexus-stage-repo-create`` returns all
arrive here, with no level prefix, whatever the log level.

**stderr** carries diagnostics: progress, warnings and failures. These
carry a level and respond to ``--debug``.

The split lets a pipeline consume a result without a warning corrupting
it:

.. code-block:: bash

   lftools-uv openstack --os-cloud vex image list | grep ubuntu
   lftools-uv rtd project-version-details onap-cps latest --json | jq '.active'

Silencing diagnostics never silences the result, and raising the
verbosity never contaminates it.
