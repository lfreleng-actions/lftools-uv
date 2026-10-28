# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Application-wide mutable state container for lftools-uv CLI.

This module centralizes shared state that was previously stored in a raw
Click context object (ctx.obj) as a plain dictionary. Using a structured
dataclass improves:

* Discoverability / IDE autocompletion
* Type-annotated hand-off to future Typer migration
* Avoids accidental context overwrites (e.g. replacing ctx.obj entirely)
* Provides helper utilities for consistent credential & client handling

Integration (incremental):

1. In the root CLI initialization, create an AppState instance and attach
   it under ctx.obj['state'] (keeping legacy keys for backward compatibility):
       state = AppState(debug=debug, interactive=interactive)
       ctx.obj.setdefault('state', state)
       state.update_credentials(username, password)

2. In subcommands that previously overwrote ctx.obj (e.g. nexus2/nexus3),
   set client references instead:
       state = ctx.obj.get('state')
       if state:
           state.nexus3 = Nexus3(fqdn=fqdn)

3. Gradually replace direct uses of ctx.obj['username'] with
   ctx.obj['state'].username (after ensuring all call sites updated).

NOTE: To avoid import-time side effects and circular dependencies, this
module deliberately does not import concrete client implementation
classes (Jenkins, Nexus, etc.). Attribute types are annotated as 'Any'.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

MASK = "********"

_LAZY_FIELDS = frozenset({"_factory", "_known", "_client"})


class LazyClient:
    """Stand-in for a service client that builds it on first use.

    Group callbacks register one in place of the client, so a subcommand's
    ``--help`` needs no configuration and a failed build surfaces in the
    command that uses the client, inside its own error handling.

    Args:
        factory: Zero-argument callable returning the real client.
        **known: Attributes answered without building the client.
    """

    def __init__(self, factory: Callable[[], Any], **known: Any) -> None:
        self._factory = factory
        self._known = known
        self._client: Any = None

    def __getattr__(self, name: str) -> Any:
        # Called only for attributes the wrapper lacks. Refusing dunders keeps
        # copy, pickle and introspection from building a client by accident;
        # refusing the wrapper's own fields avoids recursing before __init__.
        if (name.startswith("__") and name.endswith("__")) or name in _LAZY_FIELDS:
            raise AttributeError(name)
        if name in self._known:
            return self._known[name]
        if self._client is None:
            self._client = self._factory()
        return getattr(self._client, name)


@dataclass
class AppState:
    """Dataclass representing global CLI runtime state.

    Attributes:
        debug: Whether debug logging is enabled.
        interactive: Whether interactive prompting is allowed.
        username: Auth username (may be loaded from config or prompted).
        password: Auth password (never logged in clear text).
        jenkins: Cached Jenkins client instance.
        nexus2: Cached Nexus2 client instance.
        nexus3: Cached Nexus3 client instance.
        extra: Free-form dictionary for feature-specific ephemeral data.
    """

    debug: bool = False
    interactive: bool = False
    username: str | None = None
    password: str | None = None

    # Lazy-loaded / optional external service clients
    jenkins: Any = None
    nexus2: Any = None
    nexus3: Any = None

    # Arbitrary additional state storage
    extra: dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Credential handling
    # ------------------------------------------------------------------
    def update_credentials(self, username: str | None, password: str | None) -> None:
        """Set or update credential fields if provided (non-None)."""
        if username is not None:
            self.username = username
        if password is not None:
            self.password = password

    # ------------------------------------------------------------------
    # Client registration helpers
    # ------------------------------------------------------------------
    def set_client(self, name: str, client: Any) -> None:
        """Register a service client by attribute name (e.g. 'jenkins')."""
        setattr(self, name, client)

    def get_client(self, name: str) -> Any:
        """Retrieve a previously registered client (returns None if absent)."""
        return getattr(self, name, None)

    # ------------------------------------------------------------------
    # Convenience / inspection
    # ------------------------------------------------------------------
    def as_dict(self, redact_secrets: bool = True) -> Mapping[str, Any]:
        """Return a shallow dict view of state for diagnostics / debugging.

        Args:
            redact_secrets: If True, masks secret fields (currently password).

        NOTE: Avoid logging this at INFO level in production unless you
        explicitly intend to surface current state (minus secrets).
        """
        data = {
            "debug": self.debug,
            "interactive": self.interactive,
            "username": self.username,
            "password": MASK if (redact_secrets and self.password) else self.password,
            "jenkins": type(self.jenkins).__name__ if self.jenkins else None,
            "nexus2": type(self.nexus2).__name__ if self.nexus2 else None,
            "nexus3": type(self.nexus3).__name__ if self.nexus3 else None,
            "extra_keys": list(self.extra.keys()),
        }
        return data

    # ------------------------------------------------------------------
    # Mutators for extra data
    # ------------------------------------------------------------------
    def put_extra(self, key: str, value: Any) -> None:
        """Store an arbitrary value under extra."""
        self.extra[key] = value

    def get_extra(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from extra."""
        return self.extra.get(key, default)

    # ------------------------------------------------------------------
    # Debug helpers
    # ------------------------------------------------------------------
    def describe(self) -> str:
        """Return a human-readable summary line (with redacted secrets)."""
        return (
            f"AppState(debug={self.debug}, interactive={self.interactive}, "
            f"username={self.username}, password={'set' if self.password else 'unset'}, "
            f"jenkins={'yes' if self.jenkins else 'no'}, "
            f"nexus2={'yes' if self.nexus2 else 'no'}, "
            f"nexus3={'yes' if self.nexus3 else 'no'}, "
            f"extra_keys={list(self.extra.keys())})"
        )
