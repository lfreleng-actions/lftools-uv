.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

***
rtd
***

.. program-output:: lftools-uv rtd --help

Machine-readable output
=======================

Every command accepts ``--json`` and emits a parsable payload on
stdout. Diagnostics go to stderr, so a caller may parse stdout without
a warning corrupting the stream.

.. code-block:: bash

   lftools-uv rtd project-version-details onap-cps latest --json | jq '.active'

The flag works before or after the subcommand:

.. code-block:: bash

   lftools-uv rtd --json project-list
   lftools-uv rtd project-list --json

Commands that return a collection always include the collection in the
``--json`` payload, empty when nothing matches, so a parser needs no
special case for the empty result. Table output prints a short message
such as ``No projects found`` instead.

Branch names and version slugs
==============================

Read the Docs addresses a version by its **slug**, which lowercases the
branch name and replaces every character outside ``[a-z0-9._-]`` with a
hyphen. Read the Docs holds a branch named ``maintenance/3.7.10`` under
the slug ``maintenance-3.7.10``.

Passing a raw branch name to the API produces a request path that does
not resolve. Commands that accept a version offer ``--from-branch``,
which performs the conversion:

.. code-block:: bash

   lftools-uv rtd project-build-trigger onap-cps maintenance/3.7.10 --from-branch

Omit the flag when you already hold a slug.

Commands
========

project-list
------------

.. program-output:: lftools-uv rtd project-list --help

project-details
---------------

.. program-output:: lftools-uv rtd project-details --help

project-create
--------------

.. program-output:: lftools-uv rtd project-create --help

project-update
--------------

.. program-output:: lftools-uv rtd project-update --help

project-version-list
--------------------

.. program-output:: lftools-uv rtd project-version-list --help

project-version-details
-----------------------

.. program-output:: lftools-uv rtd project-version-details --help

project-version-update
----------------------

.. program-output:: lftools-uv rtd project-version-update --help

project-build-list
------------------

.. program-output:: lftools-uv rtd project-build-list --help

project-build-details
---------------------

.. program-output:: lftools-uv rtd project-build-details --help

project-build-trigger
---------------------

.. program-output:: lftools-uv rtd project-build-trigger --help

subproject-list
---------------

.. program-output:: lftools-uv rtd subproject-list --help

subproject-details
------------------

.. program-output:: lftools-uv rtd subproject-details --help

subproject-create
-----------------

.. program-output:: lftools-uv rtd subproject-create --help

subproject-delete
-----------------

.. program-output:: lftools-uv rtd subproject-delete --help

Configuration
=============

API requires a [rtd] section in ~/.config/lftools/lftools.ini:

.. code-block:: bash

   [rtd]
   token = REDACTED
   endpoint = https://readthedocs.org/api/v3/
