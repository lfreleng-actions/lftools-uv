.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

******
gerrit
******

.. program-output:: lftools-uv gerrit --help

Commands
========

list-project-permissions
------------------------

.. program-output:: lftools-uv gerrit list-project-permissions --help


list-project-inherits-from
--------------------------

.. program-output:: lftools-uv gerrit list-project-inherits-from --help


abandonchanges
--------------

.. program-output:: lftools-uv gerrit abandonchanges --help

addgitreview
------------

.. program-output:: lftools-uv gerrit addgitreview --help


addgithubrights
---------------

.. program-output:: lftools-uv gerrit addgithubrights --help


addfile
-------

.. program-output:: lftools-uv gerrit addfile --help


createproject
-------------

.. program-output:: lftools-uv gerrit createproject --help


create-saml-group
-----------------

.. program-output:: lftools-uv gerrit create-saml-group --help


addinfojob
----------
.. program-output:: lftools-uv gerrit addinfojob --help


.. note::

        Gerrit commands read their configuration from a section of
        :ref:`lftools.ini <lftools-ini>` named after the Gerrit server,
        such as [gerrit.example.org]. Commands that push a change need
        sob, the Signed-off-by line, and commands that clone a
        repository need email. For projects that forbid self-merge, the
        Gerrit API can submit a change with a second account from a
        [gerrit.example.org.second] section; no command uses this at
        present.


.. code-block:: none

     [gerrit.example.org]
     username = lfid
     password = password
     endpoint = https://gerrit.example.org/
     email = your@email.org
     sob = Your Name <your@email.org>

     [gerrit.example.org.second]
     username = lfid2
     password = password2

addmavenconfig
--------------
.. program-output:: lftools-uv gerrit addmavenconfig --help


An example of the lftools.ini entry for a Gerrit server making use of a full
configuration:

.. code-block:: none

     [gerrit.example.org]
     username = lfid
     password = password
     sob = Your Name <your@email.org>
     email = your@email.org
     endpoint = https://gerrit.example.org/
     default_servers = releases,snapshots,staging,site
     nexus3 = nexus3.example.org
     nexus3_ports = 10001,10002,10003,10004
     additional_credentials = {"docker.io": "dockerhub-cred", "nexus-iq": "nexus-iq-cred"}
