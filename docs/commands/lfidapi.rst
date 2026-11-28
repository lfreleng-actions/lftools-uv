.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

*******
lfidapi
*******

.. program-output:: lftools-uv lfidapi --help

Commands
========

create-group
------------

.. program-output:: lftools-uv lfidapi create-group --help

invite
-------

.. program-output:: lftools-uv lfidapi invite --help

search-members
--------------

.. program-output:: lftools-uv lfidapi search-members --help


user
----

.. program-output:: lftools-uv lfidapi user --help

match-ldap-to-info
------------------

.. program-output:: lftools-uv lfidapi match-ldap-to-info --help


API requires an [lfid] section in :ref:`lftools.ini <lftools-ini>`:

.. code-block:: bash

   [lfid]
   clientid = lf-releng-jenkins
   client_secret = REDACTED_SEE_SHARED_PASSWORD_STORAGE
   refresh_token = REDACTED_SEE_SHARED_PASSWORD_STORAGE
   token_uri = https://identity.linuxfoundation.org/oauth2/token
   url = https://identity.linuxfoundation.org/rest/auth0/og/
