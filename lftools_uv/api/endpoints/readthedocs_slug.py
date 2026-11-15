# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Read the Docs version slug generation.

Reproduces ``generate_version_slug()`` and ``_normalize()`` from
``readthedocs/builds/version_slug.py`` in readthedocs.org, which slugify
a branch name with ``unicode-slugify``. Read the Docs pins
``unicode-slugify==0.1.5``, which transliterates with ``unidecode``.
That package is not a dependency here: this module transliterates the
characters that matter for branch names and refuses the rest.
"""

from __future__ import annotations

import re
import unicodedata

#: Characters Read the Docs turns into a hyphen before slugifying.
_SLUG_TO_HYPHEN = re.compile(r"[/%!?]")

#: Punctuation Read the Docs keeps in a version slug, and strips from
#: its start.
_SLUG_OK = "-._"

#: Runs of hyphens and whitespace, which collapse into one hyphen.
_SLUG_COLLAPSE = re.compile(r"[-\s]+")

#: Latin letters with no Unicode decomposition, mapped as ``unidecode``
#: transliterates them for Read the Docs.
_SLUG_TRANSLITERATE = {
    "ß": "ss",
    "Æ": "AE",
    "æ": "ae",
    "Œ": "OE",
    "œ": "oe",
    "Ø": "O",
    "ø": "o",
    "Đ": "D",
    "đ": "d",
    "Ð": "D",
    "ð": "d",
    "Ł": "L",
    "ł": "l",
    "Þ": "Th",
    "þ": "th",
    "Ħ": "H",
    "ħ": "h",
    "Ŧ": "T",
    "ŧ": "t",
    "ı": "i",
}


def _slug_sanitize(text: str) -> str:
    """Keep letters, numbers and :data:`_SLUG_OK`; turn separators into spaces."""
    kept: list[str] = []
    for char in text:
        category = unicodedata.category(char)[0]
        if category in "LN" or char in _SLUG_OK:
            kept.append(char)
        elif category == "Z":
            kept.append(" ")
    return "".join(kept).strip()


def _slug_transliterate(branch: str, text: str) -> str:
    """Reduce ``text`` to ASCII the way Read the Docs does.

    Read the Docs transliterates with ``unidecode``. This covers the
    characters that matter for branch names, accented and other Latin
    letters, and refuses the rest rather than guess a slug that could
    address a different version.
    """
    out: list[str] = []
    for char in text:
        if char.isascii():
            out.append(char)
            continue
        base = "".join(
            _SLUG_TRANSLITERATE.get(c, c) for c in unicodedata.normalize("NFKD", char) if not unicodedata.combining(c)
        )
        if not base.isascii():
            msg = (
                f"Branch name {branch!r} contains {char!r}, which cannot be "
                "converted to a Read the Docs version slug; pass the version "
                "slug itself instead"
            )
            raise ValueError(msg)
        out.append(base)
    return "".join(out)


def generate_version_slug(branch: str) -> str:
    """Return the version slug Read the Docs generates for ``branch``.

    Read the Docs turns ``/``, ``%``, ``!`` and ``?`` into hyphens, then
    slugifies the result:

    - letters and numbers are kept, transliterated to ASCII and
      lowercased; ``é`` becomes ``e``;
    - ``-``, ``.`` and ``_`` are kept, but stripped from the start;
    - spaces become hyphens, and runs of hyphens collapse into one;
    - every other character is dropped, so ``foo+bar`` becomes
      ``foobar``.

    Args:
        branch: A git branch name, for example ``release/1.0``.

    Returns:
        The version slug, for example ``release-1.0``.

    Raises:
        ValueError: If ``branch`` is empty, slugifies to an empty string,
            or holds a character this module cannot transliterate as
            Read the Docs does.
    """
    if not branch or not branch.strip():
        msg = "Branch name cannot be empty"
        raise ValueError(msg)

    text = _slug_sanitize(unicodedata.normalize("NFKC", _SLUG_TO_HYPHEN.sub("-", branch)))
    text = _slug_sanitize(_slug_transliterate(branch, text))
    slug = _SLUG_COLLAPSE.sub("-", text).lower().lstrip(_SLUG_OK)

    if not slug:
        msg = f"Branch name {branch!r} does not yield a usable version slug"
        raise ValueError(msg)

    return slug
