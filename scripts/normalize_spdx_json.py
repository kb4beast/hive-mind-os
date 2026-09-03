#!/usr/bin/env python3
"""Normalize Syft SPDX 2.2 JSON output before standards validation."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


_SPDX_22_CREATED = re.compile(
    r"^(?P<whole>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d{1,9})?Z$"
)


class SpdxNormalizationError(ValueError):
    """Raised when input cannot be safely normalized as SPDX 2.2 JSON."""


def normalize_spdx_22(document: Any) -> dict[str, Any]:
    """Return *document* with only the proven Syft SPDX 2.2 gaps repaired."""

    if not isinstance(document, dict):
        raise SpdxNormalizationError("SPDX document must be a JSON object")
    if document.get("spdxVersion") != "SPDX-2.2":
        raise SpdxNormalizationError("SPDX document version must be exactly SPDX-2.2")

    creation_info = document.get("creationInfo")
    if not isinstance(creation_info, dict):
        raise SpdxNormalizationError("creationInfo must be a JSON object")
    created = creation_info.get("created")
    if not isinstance(created, str):
        raise SpdxNormalizationError("creationInfo.created must be a string")
    match = _SPDX_22_CREATED.fullmatch(created)
    if match is None:
        raise SpdxNormalizationError(
            "creationInfo.created must be a UTC timestamp with whole or fractional seconds"
        )
    whole_seconds = match.group("whole")
    try:
        datetime.strptime(whole_seconds, "%Y-%m-%dT%H:%M:%S")
    except ValueError as error:
        raise SpdxNormalizationError(
            "creationInfo.created is not a valid UTC calendar timestamp"
        ) from error
    creation_info["created"] = whole_seconds + "Z"

    packages = document.get("packages")
    if not isinstance(packages, list) or not packages:
        raise SpdxNormalizationError("packages must be a non-empty JSON array")
    for index, package in enumerate(packages):
        if not isinstance(package, dict):
            raise SpdxNormalizationError(f"packages[{index}] must be a JSON object")
        if "copyrightText" not in package:
            package["copyrightText"] = "NOASSERTION"
            continue
        copyright_text = package["copyrightText"]
        if not isinstance(copyright_text, str) or not copyright_text.strip():
            raise SpdxNormalizationError(
                f"packages[{index}].copyrightText must be a non-empty string"
            )

    return document


def normalize_file(path: Path) -> None:
    """Normalize one SPDX JSON document with a same-directory atomic replace."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SpdxNormalizationError(f"cannot read SPDX JSON: {error}") from error

    normalized = normalize_spdx_22(document)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    except OSError as error:
        raise SpdxNormalizationError(f"cannot replace SPDX JSON: {error}") from error
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except FileNotFoundError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize the proven Syft gaps in an SPDX 2.2 JSON document."
    )
    parser.add_argument("document", type=Path)
    arguments = parser.parse_args()
    try:
        normalize_file(arguments.document)
    except SpdxNormalizationError as error:
        parser.exit(1, f"SPDX normalization failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
