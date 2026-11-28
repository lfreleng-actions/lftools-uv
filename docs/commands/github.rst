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



Every ``github`` command reads its API token from
:ref:`lftools.ini <lftools-ini>`. It takes the ``token`` of the
``[github.<org>]`` section for the organization the command names, and
falls back to the ``token`` of ``[github]`` when that section has none.
With neither, the command exits non-zero and names both sections.

.. code-block:: ini

   [github]
   token = REDACTED

   [github.orgName]
   token = REDACTED
