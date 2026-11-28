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
       non-HTTPS URL, a name that matches more than one committee or a
       slug that matches more than one project, a redirect, or an HTTP
       error. A 403 means the token may be missing, expired or without
       access, or the committee may not exist: the API answers 403 for a
       UID that does not exist.
   * - ``2``
     - Usage error, such as a missing argument, an unknown option, or a
       category or join mode the committee service does not accept.
   * - ``3``
     - No committee has that SSO group name, no project has that slug,
       or a read answered 404. A committee or project the token cannot
       see looks the same.

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

committee list
--------------

.. program-output:: lftools-uv lfx committee list --help

Finds the project whose slug matches ``--project`` in full and prints
one line per committee the token can see, in name order, with three
tab-separated fields: the SSO group name (empty when the committee has
none), the UID and the name. The SSO option drops the committees whose
``sso_group_enabled`` is not true. ``--json`` prints a JSON array of
the committees' ``data`` objects instead.

A project with no committee the token can see prints nothing, says so
on stderr and exits ``0``. A slug no visible project has exits ``3``.

.. code-block:: bash

   lftools-uv lfx committee list --project example | cut -f1

committee members
-----------------

.. program-output:: lftools-uv lfx committee members --help

Reads every member of the committee from the committee service itself
rather than the query index, which keeps the list current. The output
lists members in username order, ignoring case, then members that have
no username, in email order. A member has no username, which is their
LFID, when no LF account owns their email address yet.

The endpoint needs the ``auditor`` relation on the committee, which a
committee writer has. Without it, or without a valid token, the API
answers 403 and the command exits ``1``.

``--format`` chooses the output:

``text``, the default
   ``username <email>``, one member per line. A member without a
   username prints as ``(no username) <email>``.

``csv``
   Four fields and no header: the committee's SSO group name (its name,
   when it has none), the username, the full name and the email
   address. Quotes surround a field holding a comma, a double quote or
   a line break, a bare carriage return included.

``info-yaml``
   One INFO.yaml committer entry per member:

   .. code-block:: yaml

          - name: 'Jane Doe'
            email: 'jdoe@example.org'
            company: 'Example Corp'
            id: 'jdoe'
            timezone: 'Unknown/Unknown'

   ``company`` is the member's organisation. When that is empty, the
   command takes the email domain without its last label, giving
   ``example`` for ``jdoe@example.org``. lftools-uv doubles an
   apostrophe in a value, keeping a name such as O'Brien valid YAML. A
   value holding a line break or another control character takes
   double quotes instead, with that character escaped, so it stays on
   one line.
   The output leaves out the ``lfservices_releng`` account and members
   without a username; stderr gives the count of members without a
   username, but not their addresses.

``--json`` prints the API's member array as it came; the command
refuses ``--json`` together with ``--format``.

committee inactive
------------------

.. program-output:: lftools-uv lfx committee inactive --help

Reports when each member of the committee last owned or reviewed a
change in Gerrit, so that a project can review its inactive
committers. It replaces ``ldap inactivecommitters`` and the
``inactivecommitters`` script. That script, still installed, now runs
this command with its two arguments and the default ``--months``.

``GERRIT_URL`` is the Gerrit host and path, such as
``gerrit.example.org/r``, with or without ``https://``. lftools-uv
refuses any other scheme, since it sends the credentials ``~/.netrc``
holds for the host, if any. It also refuses a URL carrying a user name
or password, which the report would print: put those in ``~/.netrc``.
It follows no redirect, since requests would send the ``~/.netrc``
credentials to the new URL, in clear when that is ``http://``; a
Gerrit answer that redirects is a failed query. Give the URL Gerrit
serves its REST API at.
Gerrit answers change queries without credentials too.

It reads the members as ``committee members`` does, so the token needs
the same ``auditor`` relation. Members without a username have no LFID
to ask Gerrit about: the command skips them and gives their count on
stderr. For each other member, in username order, it asks Gerrit for
the newest change they own or reviewed with an update in the last
``--months`` months, 12 by default, then, when there is none, for the
newest change at any time. It prints one line per member:

.. code-block:: text

     OK jdoe, Jane Doe, jdoe@example.org last submission or review 2026-10-30
     WARNING bob, Bob Smith, bob@example.com inactive since 2025-02-11 655 days ago
     ERROR amy, Amy Newcomer, amy@example.net has no activity
     ERROR zed, Zed Nobody, zed@example.org has no Gerrit account

A line break in a member's username, name or email prints as an
escape, such as ``\n`` or ``\r``, so each member stays on one line.

``has no Gerrit account`` means Gerrit answered HTTP 400
``Account 'USERNAME' not found``. The old script printed the account's
registration date here, which it read with ``gerrit gsql``; Gerrit 3.0
removed that command.

``--json`` prints a JSON array instead, with one object per member
holding ``username``, ``name``, ``email``, ``status`` (``ok``,
``inactive``, ``no_activity`` or ``no_account``), ``last_activity``
and ``days_ago``; the last two are ``null`` without a change.

A committee that is not found exits ``3``. Any Gerrit failure other
than an unknown account exits ``1``, after the lines printed so far, so
a Gerrit that does not answer never makes a member look inactive.
The command needs neither the ``ldap`` extra, an LDAP server nor SSH
access to Gerrit.

.. code-block:: bash

   lftools-uv lfx committee inactive gerrit.example.org/r example-gerrit-foo-committers

committee create
----------------

.. program-output:: lftools-uv lfx committee create --help

Creates a committee under the project whose slug ``--project`` names,
and replaces ``lfidapi create-group``. The token must be a writer on
the project; a 403 says the token may be missing or expired, or may
not be a writer there.

lftools-uv finds the project's UID through the query service first. When
no visible project has the slug it exits ``3`` and sends nothing else.
It then sends ``POST /committees`` with the committee's ``name``,
``category``, ``project_uid``, ``join_mode``, ``public`` and
``sso_group_enabled``, and its ``description`` when given. The defaults
are:

- ``--category Committers``;
- ``--join-mode closed``, so a committee writer adds every member, which
  suits a group whose membership an INFO.yaml file decides;
- ``--sso-group``, so the committee gets an SSO group;
- ``--private``.

``--category`` takes one of ``Ambassador``, ``Board``,
``Code of Conduct``, ``Committers``, ``Expert Group``,
``Finance Committee``, ``Government Advisory Council``,
``Legal Committee``, ``Maintainers``,
``Marketing Committee/Sub Committee``, ``Marketing Mailing List``,
``Marketing Oversight Committee/Marketing Advisory Committee``,
``Newsletter``, ``Other``, ``Product Security``,
``Special Interest Group``, ``Technical Advisory Committee``,
``Technical Mailing List``, ``Technical Oversight Committee``,
``Technical Steering Committee`` and ``Working Group``. ``--join-mode``
takes ``open``, ``invite_only``, ``application`` or ``closed``.
lftools-uv refuses any other value as a usage error before it sends a
request.

On success it prints one line with two tab-separated fields: the SSO
group name the service gave the committee, empty when it gave none, and
the committee's UID. ``--json`` prints the response body instead. When
the project already has a committee of that name the service answers
409, and the command exits ``1`` with the service's message, as it does
for any other error.

The SSO group name
~~~~~~~~~~~~~~~~~~

The caller cannot choose the SSO group name. With an SSO group, or with
``--public``, the service builds it from the project's slug, a hyphen
and the committee's name: project ``example`` and name
``gerrit-foo-committers`` give ``example-gerrit-foo-committers``. When
another committee already holds that name it appends ``-2``, then ``-3``,
and so on. So use the name this command prints, never one you worked
out yourself: pass that name to ``gerrit create-saml-group`` and
``gerrit createproject``.

Keep the command's output and check its exit status before you take the
first field. A pipeline such as ``create ... | cut -f1`` reports the
status of ``cut``, so a failed create would leave an empty name and the
script would go on:

.. code-block:: bash

   created="$(lftools-uv lfx committee create --project example \
       --name gerrit-foo-committers)" || exit
   group="$(printf '%s\n' "$created" | cut -f1)"
   [ -n "$group" ] || { echo "no SSO group name" >&2; exit 1; }

The query service trails the committee service by a moment, so
``committee show`` may not find the new committee by its SSO group name
straight away. Its UID skips the query service, but the service also
grants access to a new committee asynchronously, so a read by UID
straight after the create may still answer 403 and exit ``1``. A script
that reads the new committee should use its UID and retry a bounded
number of times before it gives up:

.. code-block:: bash

   uid="$(printf '%s\n' "$created" | cut -f2)"
   for try in 1 2 3 4 5; do
       lftools-uv lfx committee show "$uid" && break
       [ "$try" -lt 5 ] || exit 1
       sleep 2
   done

From lfidapi create-group
~~~~~~~~~~~~~~~~~~~~~~~~~

``lfidapi create-group GROUP`` took the full group name. Split it into
the project's slug and the rest:

.. code-block:: bash

   # Before
   lftools-uv lfidapi create-group example-gerrit-foo-committers

   # After
   lftools-uv lfx committee create --project example --name gerrit-foo-committers

Replacing the LDAP and LFID API commands
----------------------------------------

.. list-table::
   :header-rows: 1

   * - Old
     - New
   * - ``lfidapi search-members GROUP``
     - ``lfx committee members GROUP``
   * - ``ldap csv GROUP``
     - ``lfx committee members GROUP --format csv``
   * - ``ldap yaml4info GROUP``
     - ``lfx committee members GROUP --format info-yaml``
   * - ``ldap inactivecommitters GERRIT_URL GROUP``
     - ``lfx committee inactive GERRIT_URL GROUP``

The output matches the old commands for one group, with two fixes: CSV
quotes a field holding a comma or a line break, and INFO.yaml doubles
an apostrophe in a value and escapes a line break or other control
character. ``committee inactive`` describes how its report differs.
``ldap csv`` took more than one group, and LDAP wildcards, in one call.
The ``lfx committee`` commands take one committee: run them once per
committee.
