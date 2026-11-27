.. SPDX-FileCopyrightText: 2026 The Linux Foundation
..
.. SPDX-License-Identifier: EPL-1.0

***
lfx
***

.. program-output:: lftools-uv lfx --help

The ``lfx`` commands talk to the LFX v2 API, where Linux Foundation
project groups live as committees. Each committee keeps the name of the
group it replaced as its SSO group name.

Configuration
=============

API base URL
------------

lftools-uv takes the first of:

1. the ``LFX_API_URL`` environment variable;
2. ``url`` in the ``[lfx]`` section of ``lftools.ini``;
3. ``https://lfx-api.v2.cluster.lfx.dev``, the production environment.

.. code-block:: ini

   [lfx]
   url = https://lfx-api.v2.cluster.lfx.dev

The other environments are:

- staging: ``https://lfx-api.staging.v2.cluster.linuxfound.info``
- development: ``https://lfx-api.dev.v2.cluster.linuxfound.info``

A token works against the environment that issued it and no other.
lftools-uv refuses a URL that does not start with ``https://``, so the token never
travels in clear. It also refuses a URL with a query (``?``) or fragment
(``#``), which would swallow the endpoint path lftools-uv appends to it.
The error names where the URL came from but not the URL itself, since
any part of it may hold the token.

Token
-----

lftools-uv sends a bearer token, which it takes from the ``LFX_TOKEN``
environment variable. When that is unset and the
`LFX CLI <https://github.com/linuxfoundation/lfx-cli>`_ is on ``PATH``,
it runs ``lfx auth token`` and uses what that prints. With neither, the
command fails and names both.

To get a token, install the LFX CLI and log in once:

.. code-block:: bash

   lfx auth login

Then either leave ``LFX_TOKEN`` unset, or export the token:

.. code-block:: bash

   export LFX_TOKEN="$(lfx auth token)"

lftools-uv never accepts the token as a command-line option or from
``lftools.ini``, and never prints or logs it, ``--debug`` included.
Where the token turns up in what it would print, such as the committee
argument or a field of the API's answer, it prints ``<redacted>`` in
its place, and does the same for the token's URL-encoded forms. A
number, ``true``, ``false`` or ``null`` in which the token turns up
prints as that text with the token replaced, so ``--json`` shows it as
a string.

The API does not reject a missing, invalid or expired token: it serves
the request as anonymous, which sees public committees and nothing
else. So lftools-uv refuses a token that is a JWT whose ``exp`` claim
has passed before it sends anything, and checks again before each later
request, so a token that expires during a lookup stops it. It reads the
claim without checking the signature; the API checks that.

lftools-uv also refuses a token holding whitespace, a control character
or a non-ASCII character, such as a pasted token with a line break in
it, since it cannot travel in an HTTP header.

Naming a committee
==================

Commands that take a committee accept its UID or its SSO group name. lftools-uv
reads a UUID as the UID, and anything else as an SSO group name, which
must match one committee and no more; when it matches more, the error
lists their UIDs.

The query service returns the committees the token may see and hides
the rest. It also trails the committee service by a moment, so a lookup
by name may miss a committee created a moment ago.

Exit status
===========

.. list-table::
   :header-rows: 1

   * - Status
     - Meaning
   * - ``0``
     - Success.
   * - ``1``
     - Any other failure: no token, an expired or malformed token, a
       non-HTTPS URL, a name that matches more than one committee, a
       redirect, or an HTTP error. A 403 means the token may be missing,
       expired or without access, or the committee may not exist: the API
       answers 403 for a UID that does not exist.
   * - ``2``
     - Usage error, such as a missing argument or an unknown option.
   * - ``3``
     - No committee has that SSO group name, or the API answered 404. A
       committee the token cannot see looks the same.

Results go to stdout and errors to stderr, so ``--json`` output pipes
cleanly:

.. code-block:: bash

   lftools-uv lfx committee show example-gerrit-foo-committers --json | jq '.total_members'

Commands
========

committee show
--------------

.. program-output:: lftools-uv lfx committee show --help

Prints one ``key: value`` line each for ``uid``, ``name``,
``category``, ``project_uid``, ``project_name``,
``sso_group_enabled``, ``sso_group_name``, ``join_mode``, ``public``
and ``total_members``. ``--json`` prints the API response body instead.
