.. SPDX-FileCopyrightText: 2025 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

.. _nexus:

*****
nexus
*****

.. program-output:: lftools-uv nexus --help

.. _nexus-commands:

Commands
========



.. _nexus-create:

create
------

.. program-output:: lftools-uv nexus create --help

.. _nexus-repo:

repo
^^^^

.. program-output:: lftools-uv nexus create repo --help

For details and examples, please see the nexus2 documentation.

``etc/nexus/settings.example.yaml`` and ``etc/nexus/repo-config.example.yaml``
show the shape of the two files. They ship with empty passwords: copy them
somewhere private, restrict the copies to your own account
(``chmod 600 settings.yaml repo-config.yaml``) and fill in the administrator
password and one password per repository there. Do not commit the copies.

Before contacting Nexus, the command checks the administrator credentials and
every repository password in the tree, nested ones included. If any is
missing, empty, still a placeholder such as ``${NEXUS_PASSWORD}`` or
``<password>``, holds a ``${...}`` placeholder anywhere, as in
``deploy-${NEXUS_PASSWORD}``, or is not a string (YAML reads an unquoted ``false`` or ``12345``
as another type, so quote such values), it names the setting or repository
path, provisions nothing and exits non-zero. The command does not expand
placeholders, so fill in real values. ``nexus create role`` and
``nexus reorder-staged-repos`` apply the same check to the administrator
credentials in their settings file.

.. _nexus-role:

role
^^^^

.. program-output:: lftools-uv nexus create role --help

.. code-block:: yaml

   # Example role-config.yaml. The top-level keys will be the role's id.
   ---
   # Minimal config
   lf-deployment:
     display_name: LF Deployment Role
     roles: # Define roles by ID or by Name
       - nx-deployment
       - analytics
   # Full config with privileges (by name) and description defined.
   LF Deployment By Name:
     display_name: LF Dep Role
     privileges:
       - Status - (read)
       - Login to UI
     roles:
       - Nexus Deployment Role
       - Analytics
     description: "A role where I defined its contained roles by name"


.. _nexus-reorder-staged-repos:

reorder-staged-repos
--------------------

.. program-output:: lftools-uv nexus reorder-staged-repos --help

.. _nexus-docker:

docker
------

.. program-output:: lftools-uv nexus docker --help

While a settings.yaml file is still supported for ``nexus docker`` commands,
the preferred way to login is to use an lftools-uv.ini file, and provide the
server address using the ``--server`` option. The config file should be at
$HOME/.config/lftools-uv/lftools-uv.ini.

.. _nexus-docker-delete:

delete
^^^^^^

.. program-output:: lftools-uv nexus docker delete --help

.. _nexus-docker-list:

list
^^^^

.. program-output:: lftools-uv nexus docker list --help

.. _nexus-release:

release
-------

.. program-output:: lftools-uv nexus release --help

While a settings.yaml file is still supported for ``nexus release`` commands,
the preferred way to login is to use an lftools-uv.ini file, and provide the
server address using the ``--server`` option. The config file should be at
$HOME/.config/lftools-uv/lftools-uv.ini.
Requires an [nexus.example.com] for each Nexus repositories in
~/.config/lftools-uv/lftools-uv.ini:

.. code-block:: bash

   [nexus.example.com]
   username=
   password=
