# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""
Centralized error handling utilities for lftools-uv CLI commands.

Rationale
---------
Historically many commands implemented ad-hoc try/except blocks (or none at all),
calling ``sys.exit()`` directly or letting tracebacks escape. This module provides
decorators and helper functions to standardize:

* Logging format & severity
* Exit codes
* Optional debug-mode tracebacks
* Graceful fallback for optional dependencies (e.g., ldap)
* Extensibility for future Typer migration (decorator is framework-agnostic)

Usage
-----
Example for a Click command::

    import click
    from lftools_uv.cli.errors import handle_errors

    @click.command()
    @handle_errors()
    def mycmd():
        # raise requests.HTTPError, yaml.YAMLError, etc.
        ...

Decorator Parameters
--------------------
``@handle_errors(
    exit_codes = {ExceptionType: int, ...},
    default_exit_code = 1,
    reraise = False,
    include = (ExceptionTypeA, ExceptionTypeB, ...),
    exclude = (SomeExceptionType,),
)``

If ``reraise=True``, matched exceptions are logged then re-raised (useful for tests).

Exit Codes
----------
You can override or extend exit code mappings via the ``exit_codes`` parameter.
Generic fallback uses ``default_exit_code`` (default = 1).

Debug Mode
----------
If root state (ctx.obj) has debug=True, full tracebacks are logged at
ERROR level for handled exceptions; otherwise only succinct messages are shown.

Thread-safety / Reentrancy
--------------------------
State inspection is read-only; decorator keeps no global mutable state.

Limitations
-----------
* The decorator is synchronous; it does not specially handle asyncio tasks.
* If used outside Click, absence of a context is handled gracefully.

"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable, Iterable, Mapping, MutableMapping
from functools import wraps
from types import ModuleType
from typing import TYPE_CHECKING, ParamSpec, TypeVar

# Optional import guarded to avoid hard dependency on Click
click: ModuleType | None
try:
    import click as _click_module
except Exception:  # pragma: no cover - defensive
    click = None
else:
    click = _click_module

if TYPE_CHECKING:
    import click as _click_type

log: logging.Logger = logging.getLogger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


# Default exit code mapping for common exception classes
DEFAULT_EXIT_CODES: dict[str, int] = {
    "HTTPError": 2,
    "LDAPError": 3,
    "YAMLError": 4,
    "NoSectionError": 5,
    "NoOptionError": 6,
    "FileNotFoundError": 7,
    "PermissionError": 8,
    # Generic fallback -> 1
}


def _exception_key(exc: BaseException) -> str:
    """Return a canonical key name for an exception class."""
    return exc.__class__.__name__


def _resolve_exit_code(
    exc: BaseException,
    exit_codes: Mapping[str, int],
    default_exit_code: int,
) -> int:
    """Resolve exit code for an exception."""
    key: str = _exception_key(exc)
    return exit_codes.get(key, default_exit_code)


def _in_debug_mode() -> bool:
    """Attempt to detect global debug mode from Click context state."""
    if not click:
        return False
    try:
        ctx: _click_type.Context | None = click.get_current_context(silent=True)
        if not ctx:
            return False
        obj: object = ctx.obj  # pyright: ignore[reportAny]
        if isinstance(obj, MutableMapping):
            state: object = obj.get("state")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            if state and getattr(state, "debug", False):  # pyright: ignore[reportUnknownArgumentType]
                return True
            # Backward compatibility: ctx.obj["DEBUG"]
            if obj.get("DEBUG"):  # pyright: ignore[reportUnknownMemberType]
                return True
    except Exception:  # pragma: no cover - safety net
        return False
    return False


def _log_exception(exc: BaseException, show_traceback: bool) -> None:
    """Log an exception uniformly."""
    if show_traceback:
        log.error("Unhandled exception (%s): %s", exc.__class__.__name__, exc)
        tb: str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        log.error(tb)
    else:
        log.error("%s: %s", exc.__class__.__name__, exc)


def handle_errors(
    *,
    exit_codes: Mapping[str, int] | None = None,
    default_exit_code: int = 1,
    reraise: bool = False,
    include: Iterable[type[BaseException]] | None = None,
    exclude: Iterable[type[BaseException]] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorate to standardize error handling for CLI commands.

    Args:
        exit_codes:
            Mapping of exception class name -> exit code (overrides defaults).
        default_exit_code:
            Fallback code when an exception class is not in mapping.
        reraise:
            If True, after logging re-raise the exception (testing / higher-level handling).
        include:
            If provided, only these exception types (or subclasses) are caught & processed.
        exclude:
            If provided, these exception types are never caught (re-raised immediately).

    Returns:
        Wrapped function with standardized exception handling.
    """
    # Merge custom mapping atop defaults
    merged_codes: dict[str, int] = {**DEFAULT_EXIT_CODES}
    if exit_codes:
        merged_codes.update(exit_codes)

    include_types: tuple[type[BaseException], ...] | None = tuple(include) if include else None
    exclude_types: tuple[type[BaseException], ...] | None = tuple(exclude) if exclude else None

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        """Wrap function with error handling."""

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            """Execute wrapped function with error handling."""
            debug_mode: bool = _in_debug_mode()
            try:
                return func(*args, **kwargs)
            except SystemExit:
                # Allow explicit sys.exit / click.Abort to propagate unchanged
                raise
            except BaseException as exc:  # noqa: BLE001 - we intentionally centralize handling
                # Inclusion / exclusion logic
                if exclude_types and isinstance(exc, exclude_types):
                    raise
                if include_types and not isinstance(exc, include_types):
                    raise

                _log_exception(exc, show_traceback=debug_mode)
                code: int = _resolve_exit_code(exc, merged_codes, default_exit_code)

                if reraise:
                    raise
                # Attempt to exit via Click if available to honor Click's flow
                if click:
                    ctx_inner: _click_type.Context | None = click.get_current_context(silent=True)
                    if ctx_inner:
                        ctx_inner.exit(code)
                # Fallback
                raise SystemExit(code) from None  # pragma: no cover (rare fallback path)

        return wrapper

    return decorator


# Convenience alias with default behavior
error_handler = handle_errors()


__all__: list[str] = [
    "handle_errors",
    "error_handler",
    "AppState",  # re-export optional for convenience if imported after state
]

# Optional re-export if state module already loaded (avoid circular import)
try:  # pragma: no cover - optional convenience
    from .state import AppState  # noqa: F401
except Exception:  # pragma: no cover
    pass
