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
       no member of the committee matches, or a read answered 404. A
       committee or project the token cannot see looks the same.

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

Committee membership
--------------------

Membership is by email address. ``lfidapi user`` named an LFID alone;
``add-member`` needs the person's email address, and the committee
service finds the LF account that owns it. ``--username`` checks that
the address belongs to the LFID you meant.

The service emails a member it adds or removes. LDAP group changes sent
no email, so these commands send ``X-Skip-Notification: true`` to stop
it; ``--notify`` lets the email go.

No diagnostic on stderr carries an email address, not even one quoted
in the service's message or given as a username or as the committee's
SSO group name, with an apostrophe in its local part such as
``o'connor@example.org`` or ``'@example.org``, a quoted local part such
as ``"j doe"@example.org`` or an address literal such as
``jdoe@[192.0.2.1]``; results on stdout may carry the ones you supplied.

committee add-member
~~~~~~~~~~~~~~~~~~~~

.. program-output:: lftools-uv lfx committee add-member --help

Sends ``POST /committees/{uid}/members`` with ``email`` and any of
``first_name``, ``last_name`` and ``organization.name`` given. The token
must be a ``writer`` on the committee.

- The service sets the member's username itself, from the LF account
  that owns the address, and stores none when no account owns it. It
  fills an empty first or last name from that account, then requires
  both.
- A committee with voting or business email enabled also requires an
  organisation with an ID, or a name and a website, which this command
  cannot send.

On success it prints one line with three tab-separated fields:
``added``, the username the service resolved, and the member UID. A
member with no username prints ``(no username)``, and stderr warns that
no LF account owns the address yet. ``--json`` prints the member object
instead.

With ``--username LFID`` the command compares, ignoring case, the
username the service resolved with ``LFID``. When they differ, or the
address resolved to no username, it removes the member it added a
moment before and exits ``1``, saying which username the address
resolved to. The command thus either makes that LFID a member or
changes nothing. When the removal fails too, the error says so and
gives the member UID, for you to remove by hand. An empty ``LFID`` is a
usage error, exit ``2``, and sends nothing, since it would match a
member with no username.

When the address is already a member the service answers 409. The
command then finds that member in the member list by its address,
ignoring case and surrounding whitespace as the service does, and
reports its username and member UID on stderr. It exits ``0``, or
``1`` when ``--username`` names another account. It never removes a
member that was there before it ran.

Any other error, such as a 400 for a missing name, exits ``1`` with the
service's message.

committee remove-member
~~~~~~~~~~~~~~~~~~~~~~~

.. program-output:: lftools-uv lfx committee remove-member --help

Name the member with one of ``--username``, ``--email`` and
``--member-uid``; giving none, or more than one, is a usage error. The
command matches a username or an email address, ignoring case, against
the member list, which needs the ``auditor`` relation that a committee
writer has. An email address also matches without surrounding
whitespace. No match exits ``3``; more than one exits ``1`` and lists
their member UIDs, so you can name one with ``--member-uid``.

The command reads the member for its ``ETag`` and sends
``DELETE /committees/{uid}/members/{member_uid}`` with that value in
``If-Match``. When the member changed after that read, the service
answers 409, and the command reads the member again and retries once.
The token must be a ``writer`` on the committee. On success it prints
``removed`` and the member UID, separated by a tab.

committee invite
~~~~~~~~~~~~~~~~

.. program-output:: lftools-uv lfx committee invite --help

Sends ``POST /committees/{uid}/invites`` for the email address. The
token needs the ``inviter`` relation on the committee. On success it
prints the invite UID and its status, ``pending``, separated by a tab;
``--json`` prints the invite object instead. When a pending invite
exists for the address, or its holder is a member already, the
service answers 409 and the command exits ``1`` with the service's
message.

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
   * - ``lfidapi user LFID GROUP``
     - ``lfx committee add-member GROUP --email EMAIL --username LFID``
   * - ``lfidapi user LFID GROUP --delete``
     - ``lfx committee remove-member GROUP --username LFID``
   * - ``lfidapi invite EMAIL GROUP``
     - ``lfx committee invite GROUP EMAIL``

The member listings match the old commands for one group, with two
fixes: CSV quotes a field holding a comma or a line break, and
INFO.yaml doubles an apostrophe in a value and escapes a line break
or other control character.
``ldap csv`` took more than one group, and LDAP wildcards, in one call.
``lfx committee members`` takes one committee: run it once per
committee.
