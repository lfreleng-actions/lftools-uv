.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

******
github
******

.. program-output:: lftools-uv github --help

Commands
========

create-repo
-----------

.. program-output:: lftools-uv github create-repo --help

create-team
-----------

.. program-output:: lftools-uv github create-team --help


list
----

.. program-output:: lftools-uv github list --help


update-repo
-----------

.. program-output:: lftools-uv github update-repo --help


submit-pr
---------

.. program-output:: lftools-uv github submit-pr --help


user
----

.. program-output:: lftools-uv github user --help


votes
-----

.. program-output:: lftools-uv github votes --help



API requires a [github] or [github.OrgName] section in :ref:`lftools.ini <lftools-ini>`:

.. code-block:: bash

   [github] or [github.orgName]
   token = REDACTED
