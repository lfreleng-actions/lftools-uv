# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Test utilities for lftools-uv.

This module provides utility functions for testing, including ANSI escape
sequence stripping to handle Rich-formatted output in tests.
"""

import re

# Environment for CliRunner.invoke() calls that render --help at a fixed
# width. CliRunner inherits every variable it does not name, and Rich
# pins a forced terminal with TERM=dumb at 80 columns, ignoring COLUMNS,
# so TERM is removed (a None value unsets it).
HELP_ENV: dict[str, str | None] = {"COLUMNS": "200", "NO_COLOR": "1", "TERM": None}


def strip_ansi_codes(text: str) -> str:
    """Strip ANSI escape sequences from text.

    This function removes ANSI color codes, formatting codes, and other
    terminal escape sequences from the given text. This is useful for
    testing CLI output that may contain Rich formatting.

    Args:
        text: The text to strip ANSI codes from

    Returns:
        The text with all ANSI escape sequences removed

    Example:
        >>> strip_ansi_codes("\\x1b[1mBold\\x1b[0m text")
        'Bold text'
    """
    # ANSI escape sequence pattern
    # Matches ESC[ followed by any number of parameter bytes (0x30-0x3F)
    # followed by any number of intermediate bytes (0x20-0x2F)
    # followed by a final byte (0x40-0x7E)
    ansi_escape = re.compile(r"\x1b\[[0-9;]*[mK]")

    # More comprehensive pattern that covers all ANSI escape sequences
    comprehensive_ansi = re.compile(
        r"\x1b"  # ESC character
        + r"(?:"  # Non-capturing group for different types
        + r"\[[0-9;]*[a-zA-Z]"  # CSI sequences (most common)
        + r"|"
        + r"\][^\x07]*\x07"  # OSC sequences ending with BEL
        + r"|"
        + r"\][^\x1b]*\x1b\\"  # OSC sequences ending with ST
        + r"|"
        + r"[(\)][AB012]"  # Character set sequences
        + r"|"
        + r"[=>]"  # Application keypad sequences
        + r"|"
        + r"[78]"  # Save/restore cursor
        + r"|"
        + r"M"  # Reverse line feed
        + r"|"
        + r"D"  # Line feed
        + r"|"
        + r"E"  # New line
        + r"|"
        + r"H"  # Tab set
        + r"|"
        + r"Z"  # Return terminal ID
        + r")"
    )

    # Apply both patterns to be thorough
    text = ansi_escape.sub("", text)
    text = comprehensive_ansi.sub("", text)

    return text


def clean_cli_output(output: str) -> str:
    """Clean CLI output for testing.

    This function performs comprehensive cleaning of CLI output including:
    - Stripping ANSI escape sequences
    - Normalizing whitespace
    - Removing extra newlines

    Args:
        output: The raw CLI output to clean

    Returns:
        Cleaned output suitable for string matching in tests
    """
    # Strip ANSI codes first
    cleaned = strip_ansi_codes(output)

    # Normalize line endings
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

    # Remove excessive whitespace but preserve structure
    lines = cleaned.split("\n")
    cleaned_lines = []

    for line in lines:
        # Strip trailing whitespace but preserve leading whitespace for indentation
        cleaned_line = line.rstrip()
        cleaned_lines.append(cleaned_line)

    # Join back together
    cleaned = "\n".join(cleaned_lines)

    # Remove excessive empty lines (more than 2 consecutive)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    return cleaned


def assert_in_output(expected: str, output: str, message: str | None = None) -> None:
    """Assert that expected text is in cleaned CLI output.

    This is a convenience function that strips ANSI codes before assertion.

    Args:
        expected: The text expected to be found
        output: The CLI output to search in
        message: Optional custom assertion message

    Raises:
        AssertionError: If expected text is not found in cleaned output
    """
    cleaned_output = clean_cli_output(output)

    if message is None:
        message = f"Expected '{expected}' not found in cleaned output"

    assert expected in cleaned_output, f"{message}\n\nCleaned output:\n{cleaned_output}"


def assert_not_in_output(unexpected: str, output: str, message: str | None = None) -> None:
    """Assert that unexpected text is NOT in cleaned CLI output.

    Args:
        unexpected: The text that should not be found
        output: The CLI output to search in
        message: Optional custom assertion message

    Raises:
        AssertionError: If unexpected text is found in cleaned output
    """
    cleaned_output = clean_cli_output(output)

    if message is None:
        message = f"Unexpected '{unexpected}' found in cleaned output"

    assert unexpected not in cleaned_output, f"{message}\n\nCleaned output:\n{cleaned_output}"
