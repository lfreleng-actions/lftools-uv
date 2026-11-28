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



API for check votes requires a [github] section in :ref:`lftools.ini <lftools-ini>`:

.. code-block:: bash

   [github]
   token = REDACTED
