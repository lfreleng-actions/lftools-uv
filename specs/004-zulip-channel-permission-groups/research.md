<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- tables preserve exact Zulip URLs/field names -->

# Research: Zulip Channel Permission Groups

## Authoritative Zulip API Sources

- Create channel overview: <https://zulip.com/api/create-stream>
- Create/subscribe endpoint used by this project:
  <https://zulip.com/api/subscribe>
- Update channel endpoint: <https://zulip.com/api/update-stream>
- Read channel detail endpoint: <https://zulip.com/api/get-stream-by-id>
- Group-setting value format:
  <https://zulip.com/api/group-setting-values>
- Ignored unsupported request parameters:
  <https://zulip.com/api/rest-error-handling#ignored-parameters>
- API feature-level changelog: <https://zulip.com/api/changelog>

The `create-stream` page explicitly states that channel creation is done by
submitting a subscribe request with a channel name that does not yet exist and
passing optional initial settings. Therefore the create facts below use the
`POST /api/v1/users/me/subscriptions` documentation.

## Verified API Field Inventory

| Zulip field | Meaning | Feature level | Create support | Update support | Read support | Value shape | Sources |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `can_add_subscribers_group` | Who can add other users to the channel | 342 | Yes, optional parameter on `POST /users/me/subscriptions` | Yes, optional parameter on `PATCH /streams/{stream_id}` | Yes, returned by get-stream-by-id | Create/read use group-setting value: integer group ID or object with `direct_members` and `direct_subgroups`. Update uses group-setting update object with required `new` and optional `old`; `new` is the same integer-or-object value. | <https://zulip.com/api/subscribe#parameter-can_add_subscribers_group>, <https://zulip.com/api/update-stream#parameter-can_add_subscribers_group>, <https://zulip.com/api/get-stream-by-id>, <https://zulip.com/api/group-setting-values> |
| `can_administer_channel_group` | Who can administer the channel | 325 | Yes, optional parameter on `POST /users/me/subscriptions` | Yes, optional parameter on `PATCH /streams/{stream_id}` | Yes, returned by get-stream-by-id | Create/read use group-setting value. Update uses group-setting update object with required `new` and optional `old`. | <https://zulip.com/api/subscribe#parameter-can_administer_channel_group>, <https://zulip.com/api/update-stream#parameter-can_administer_channel_group>, <https://zulip.com/api/get-stream-by-id>, <https://zulip.com/api/group-setting-values> |
| `can_send_message_group` | Who can post messages in the channel | 333 | Yes, optional parameter on `POST /users/me/subscriptions` | Yes, optional parameter on `PATCH /streams/{stream_id}` | Yes, returned by get-stream-by-id | Create/read use group-setting value. Update uses group-setting update object with required `new` and optional `old`. | <https://zulip.com/api/subscribe#parameter-can_send_message_group>, <https://zulip.com/api/update-stream#parameter-can_send_message_group>, <https://zulip.com/api/get-stream-by-id>, <https://zulip.com/api/group-setting-values> |

### Field-Name Verification

The official docs spell the field names exactly as:

- `can_add_subscribers_group`
- `can_administer_channel_group`
- `can_send_message_group`

No `can_access_group` field appears in the official channel create, update, or
read documentation. Zulip's REST API can return `ignored_parameters_unsupported`
in successful responses when unsupported parameters are sent, so exact field
names and feature-level gates are mandatory rather than relying on success
responses.

### Feature-Level Verification

Endpoint docs provide the exact feature levels in each field's **Changes**
entry:

- `can_add_subscribers_group`: "New in Zulip 10.0 (feature level 342)."
- `can_administer_channel_group`: "New in Zulip 10.0 (feature level 325)."
- `can_send_message_group`: "New in Zulip 10.0 (feature level 333)."

The changelog has corresponding feature-level headings for 342, 333, and 325;
the endpoint docs carry the full field-specific descriptions.

### Value-Shape Verification

The group-setting values page defines a group-setting value as either:

1. an integer user group ID, or
2. an object with `direct_members: list[int]` and
   `direct_subgroups: list[int]`.

The same page defines a group-setting update object for updates as an object
with required `new` and optional `old`. The update docs for each of the three
fields use that update object shape. The create docs for each of the three
fields use the raw group-setting value shape directly.

### Clearing or Resetting Verification

The official create and update docs for these three fields document only an
integer group ID or object-form group-setting value. They do not document
`null`, an empty string, a `none` sentinel, or another reset-to-default value
for these settings. Because the project has already had silent data bugs from
unsupported parameters, this feature must not invent a clearing sentinel.

A user who wants a permission to be disabled may supply the `Nobody` system
role group only if the server accepts that value for the specific permission.
A user who wants the organization's conventional default must supply that
explicit group (for example `Members`, `Administrators`, or another group), not
a reset sentinel.

## Decision 1: Flag Naming Mirrors API Fields

**Decision**: Add exactly these flags:

- `--can-add-subscribers-group`
- `--can-administer-channel-group`
- `--can-send-message-group`

**Rationale**: The existing `--can-remove-subscribers-group` flag already
mirrors its API field name and is more precise than `--allow-group`. Mirroring
the API field names makes it easier to cross-reference `channel show` output,
Zulip docs, and CLI help. It also reduces the chance of introducing another
wrong field name.

**Compatibility**: `--allow-group` remains unchanged and continues to map to
`can_subscribe_group`. A future documentation-only polish may describe it as a
legacy alias for self-subscribe permission, but this feature must not rename,
remove, or deprecate it in behavior.

**Alternatives Considered**:

- Short names such as `--add-subscribers-group` or `--administer-group`:
  Rejected because they are less directly traceable to the Zulip fields and
  would create another naming convention.
- Renaming `--allow-group`: Rejected as out of scope and backwards
  incompatible.

## Decision 2: No Clearing Sentinel

**Decision**: Do not add `none`, `clear`, `--clear-*`, or `null` support for
these three flags.

**Rationale**: Official Zulip docs do not document a reset/null value for these
parameters. The folder feature used `--folder none` because `folder_id` is
documented as accepting `null`; these permission fields are not. Treating
`none` specially here would be an undocumented API assumption.

**Operational Guidance**: Users set an explicit desired group-setting value. If
they need an empty permission and the server permits it for the field, they can
use the `Nobody` system role group via the normal resolver.

## Decision 3: Feature-Level Gates Per Flag

**Decision**: Add one feature-level constant per field and check it whenever
that field is requested:

| Feature key | Required FL | Flag |
| --- | --- | --- |
| `can-add-subscribers-group` | 342 | `--can-add-subscribers-group` |
| `can-administer-channel-group` | 325 | `--can-administer-channel-group` |
| `can-send-message-group` | 333 | `--can-send-message-group` |

**Error shape**:

```text
Error: This operation requires Zulip feature level X (server has Y)
```

**Rationale**: Zulip may otherwise ignore unsupported parameters while
returning success with `ignored_parameters_unsupported`. Client-side gating is
the best defense against silent data bugs.

## Decision 4: No `stream_post_policy` Fallback

**Decision**: `--can-send-message-group` fails below FL 333 and never writes
legacy `stream_post_policy`.

**Rationale**: Official docs say `can_send_message_group` replaced
`stream_post_policy` at FL 333 and supports finer configurations. Falling back
to `stream_post_policy` would produce server-version-dependent behavior and
could silently grant broader or narrower posting rights than requested.

**Alternatives Considered**:

- Translate common system groups to `stream_post_policy` on old servers:
  Rejected because it is lossy, incomplete for object-form group-setting
  values, and repeats the class of silent compatibility bug this feature is
  designed to avoid.

## Decision 5: Stacked PR Structure Is Acceptable

**Decision**: Keep the user's requested three-way implementation split, even
though the flags are very similar.

**Rationale**: The split increases review overhead but gives reviewers one
permission field at a time, which is valuable after previous Zulip API-field
mistakes. Shared helper work must land in the first PR to minimize duplication
and keep the second and third PRs small.

**Risk**: If the first PR changes shared function signatures, the later stacked
PRs may need rebases. This is manageable because each flag touches the same
small set of files and has isolated tests.
