.. SPDX-FileCopyrightText: 2026 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

.. _lftools-ini:

###########
lftools.ini
###########

``lftools.ini`` holds the credentials and per-server settings that
lftools-uv commands read. ``lftools-uv config get`` and
``lftools-uv config set`` read and change it from the command line.

Location
========

lftools-uv reads ``lftools.ini`` from the directory that
``platformdirs.user_config_dir("lftools")`` returns:

* Linux: ``$XDG_CONFIG_HOME/lftools/lftools.ini``, which defaults to
  ``~/.config/lftools/lftools.ini``.
* macOS: ``$XDG_CONFIG_HOME/lftools/lftools.ini`` when ``XDG_CONFIG_HOME``
  has a value, otherwise
  ``~/Library/Application Support/lftools/lftools.ini``.

The directory carries the name ``lftools``, not ``lftools-uv``, so
lftools-uv and legacy lftools share one configuration.

Where the platform's directory differs from ``~/.config/lftools`` and does
not exist yet, but ``~/.config/lftools`` does, lftools-uv copies the whole
``~/.config/lftools`` directory to the platform's directory the first time
it runs, and reads from the copy from then on. Later edits to the files in
``~/.config/lftools`` have no effect. When the copy fails, lftools-uv logs
a warning and keeps reading ``~/.config/lftools``.

Permissions
===========

The file holds passwords and API tokens. Make the file that lftools-uv
reads, at the path `Location`_ gives, readable and writable by its owner
alone. On Linux:

.. code-block:: bash

   chmod 600 "${XDG_CONFIG_HOME:-$HOME/.config}/lftools/lftools.ini"

On macOS:

.. code-block:: bash

   chmod 600 "${XDG_CONFIG_HOME:-$HOME/Library/Application Support}/lftools/lftools.ini"

The copy made on the first run keeps the modes of the files in
``~/.config/lftools``, and leaves those files in place with the same
credentials: restrict or remove them too.

``lftools-uv config set`` creates a missing file with mode ``600``, and
leaves the mode of an existing file unchanged.

Sections and options
====================

The file uses INI syntax: a ``[section]`` header followed by
``option = value`` lines. A section named after a server takes the
server's host name, without ``https://``, for example
``[gerrit.example.org]``.

.. list-table::
   :header-rows: 1
   :widths: 25 30 45

   * - Section
     - Options
     - Read by
   * - ``[global]``
     - ``username``, ``password``
     - Every command, as the default for the top-level ``--username`` and
       ``--password`` options. ``jenkins token`` commands use them.
   * - ``[github]``
     - ``token``
     - ``github`` commands, ``infofile check-votes``, and
       ``lfidapi match-ldap-info`` given ``--githuborg``. ``github
       submit-pr`` reads it when ``[github.<org>]`` sets an empty
       ``token``, and not otherwise. ``lfidapi match-ldap-info``
       always needs it to add or remove team members, which it does
       unless given ``--noop``.
   * - ``[github.<org>]``
     - ``token``
     - ``github submit-pr``, and in the legacy front end ``github
       create-repo``, ``update-repo`` and ``create-team``. These fail when
       the file lacks this section or its ``token``, even with a
       ``[github]`` token. They use ``[github]`` when this ``token`` is
       empty. ``github list``, and ``lfidapi match-ldap-info`` when
       listing the team, read it when the file has no ``[github]``
       section.
   * - ``[lfid]``
     - ``clientid``, ``client_secret``, ``refresh_token``, ``token_uri``,
       ``url``
     - ``lfidapi`` commands.
   * - ``[rtd]``
     - ``token``, ``endpoint``
     - ``rtd`` commands.
   * - ``[zulip]``
     - ``email``, ``key``, ``site``
     - ``zulip`` commands, when neither ``--zuliprc`` nor ``./zuliprc``
       supplies the credentials.
   * - ``[gerrit]``
     - ``username``, ``password``
     - ``infofile create-info-file``, unless given ``--empty``.
   * - ``[<gerrit host>]``
     - ``username``, ``password``, ``endpoint``
     - ``gerrit`` commands.
   * -
     - ``sob``
     - ``gerrit addfile``, ``addinfojob``, ``addgitreview`` and
       ``addmavenconfig``, as the ``Signed-off-by`` line of the change.
   * -
     - ``email``
     - ``gerrit addinfojob``, ``addgitreview`` and ``addmavenconfig``, as
       the git ``user.email`` of the clone.
   * -
     - ``default_servers``, ``additional_credentials``, ``nexus3``,
       ``nexus3_ports``
     - ``gerrit addmavenconfig``. Each has a default, so the section may
       omit them.
   * - ``[<gerrit host>.second]``
     - ``username``, ``password``
     - The Gerrit API's ``add_git_review`` method, to submit a change on a
       project that forbids self-merge. No command calls it at present.
   * - ``[<nexus host>]``
     - ``username``, ``password``, ``endpoint``
     - ``nexus2`` and ``nexus3`` commands.
   * -
     - ``username``, ``password``
     - ``nexus release --server``, and in the legacy front end
       ``nexus create repo --url`` and ``nexus docker`` with ``--server``.

Example
=======

.. code-block:: ini

   [global]
   username = lfid
   password = REDACTED

   [github]
   token = REDACTED

   [rtd]
   token = REDACTED
   endpoint = https://readthedocs.org/api/v3/

   [gerrit.example.org]
   username = lfid
   password = REDACTED
   endpoint = https://gerrit.example.org/
   email = your@email.org
   sob = Your Name <your@email.org>

   [nexus.example.org]
   username = lfid
   password = REDACTED
   endpoint = https://nexus.example.org/

Jenkins servers and OpenStack clouds have their own files,
``jenkins_job.ini`` and ``clouds.yaml``, not sections of ``lftools.ini``.
