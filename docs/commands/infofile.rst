.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

********
infofile
********

.. program-output:: lftools-uv infofile --help

Commands
========

check-votes
-----------

 .. program-output:: lftools-uv infofile check-votes --help

get-committers
--------------

 .. program-output:: lftools-uv infofile get-committers --help

sync-committers
---------------

 .. program-output:: lftools-uv infofile sync-committers --help


Creating an info file requires a connection to the VPN
and a working openldap configuration


.. code-block:: bash

    $ cat /etc/openldap/ldap.conf
    TLS_REQCERT never
    or
    prereqs: For ldap lookups to work you must be on the VPN and have the cert to get the cert: log in to any collab system and grab /etc/ipa/ca.crt in /etc/openldap/ldap.conf, add 'TLS_CACERT /path/to/ipa.ca'


create-info-file
----------------

 .. program-output:: lftools-uv infofile create-info-file --help

The committers listed in the new INFO file are the members of one LDAP
group. By default the command derives its name as
``<umbrella>-gerrit-<project>-committers``: ``<umbrella>`` is the second
label of the Gerrit host, with ``o-ran-sc`` written as ``oran`` and
``opendaylight`` as ``odl``, and ``<project>`` is the Gerrit project with
each ``/`` and ``_`` written as ``-``. When a project's group does not
follow that pattern, name it with ``--group``:

.. code-block:: bash

    lftools-uv infofile create-info-file gerrit.example.org foo/bar --group foo-maintainers

With ``--empty`` the command contacts neither Gerrit nor LDAP and lists one
empty committer. A failed member lookup prints nothing on stdout and exits
non-zero, so it leaves no partial INFO file behind. ``--tsc-approval`` and
``--tsc_approval`` are the same option.


``check-votes --github_repo`` reads its GitHub token as the ``github``
commands do: the ``token`` of ``[github.<org>]``, otherwise that of
``[github]``, in :ref:`lftools.ini <lftools-ini>`.

.. code-block:: ini

   [github]
   token = REDACTED
