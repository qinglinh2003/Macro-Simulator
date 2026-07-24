#!/usr/bin/env python3
"""Validate native dependency pins and emit a deterministic SPDX report."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import socket
import sys
import urllib.request
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "native/dependencies.lock.json"
SBOM_PATH = ROOT / "schemas/m1/native_sbom.spdx.json"
REQUIRED_CAPABILITIES = {
    "canonical-json",
    "checkpoint-envelope",
    "npy-npz",
    "sha256",
    "zip-deflate",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def load_and_validate() -> dict[str, Any]:
    document = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if document.get("schema_version") != "m1-native-dependencies-v1":
        raise ValueError("native dependency schema version is unsupported")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list) or not dependencies:
        raise ValueError("native dependency list is empty")
    names: set[str] = set()
    capabilities: set[str] = set()
    required = {
        "name",
        "capability",
        "version",
        "immutable_ref",
        "source_url",
        "source_sha256",
        "license",
        "license_file",
        "integration",
    }
    for dependency in dependencies:
        missing = required.difference(dependency)
        if missing:
            raise ValueError(
                f"dependency record is incomplete: {', '.join(sorted(missing))}"
            )
        name = dependency["name"]
        capability = dependency["capability"]
        if name in names or capability in capabilities:
            raise ValueError("native dependency names and capabilities must be unique")
        names.add(name)
        capabilities.add(capability)
        if not dependency["source_url"].startswith("https://"):
            raise ValueError(f"dependency source is not HTTPS: {name}")
        if not SHA256_PATTERN.fullmatch(dependency["source_sha256"]):
            raise ValueError(f"dependency source hash is invalid: {name}")
        if not dependency["immutable_ref"]:
            raise ValueError(f"dependency source identity is absent: {name}")
        if not dependency["license"] or not dependency["license_file"]:
            raise ValueError(f"dependency license evidence is absent: {name}")
    if capabilities != REQUIRED_CAPABILITIES:
        missing = REQUIRED_CAPABILITIES.difference(capabilities)
        extra = capabilities.difference(REQUIRED_CAPABILITIES)
        raise ValueError(
            f"native capability set differs: missing={sorted(missing)} extra={sorted(extra)}"
        )
    if dependencies != sorted(dependencies, key=lambda item: item["name"].casefold()):
        raise ValueError("native dependencies are not sorted by name")
    return document


def build_spdx(document: dict[str, Any]) -> dict[str, Any]:
    packages = []
    for dependency in document["dependencies"]:
        package_id = re.sub(
            r"[^A-Za-z0-9.-]",
            "-",
            dependency["name"],
        )
        packages.append(
            {
                "SPDXID": f"SPDXRef-Package-{package_id}",
                "checksums": [
                    {
                        "algorithm": "SHA256",
                        "checksumValue": dependency["source_sha256"],
                    }
                ],
                "downloadLocation": dependency["source_url"],
                "externalRefs": [
                    {
                        "referenceCategory": "OTHER",
                        "referenceLocator": dependency["immutable_ref"],
                        "referenceType": "macro-sim-immutable-source-ref",
                    }
                ],
                "filesAnalyzed": False,
                "licenseConcluded": dependency["license"],
                "licenseDeclared": dependency["license"],
                "name": dependency["name"],
                "supplier": "NOASSERTION",
                "versionInfo": dependency["version"],
            }
        )
    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "creators": ["Tool: macro-sim-tools-m1-dependency-report"],
            "licenseListVersion": "3.25",
        },
        "dataLicense": "CC0-1.0",
        "documentNamespace": (
            "https://macro-sim.invalid/spdx/"
            + sha256(canonical_bytes(packages)).hexdigest()
        ),
        "name": "macro-simulator-m1-native-foundation",
        "packages": packages,
        "spdxVersion": "SPDX-2.3",
    }


def verify_downloads(document: dict[str, Any]) -> None:
    for dependency in document["dependencies"]:
        digest = sha256()
        try:
            with urllib.request.urlopen(
                dependency["source_url"],
                timeout=120,
            ) as response:
                while block := response.read(1024 * 1024):
                    digest.update(block)
        except (OSError, socket.timeout) as error:
            raise ValueError(
                f"dependency download failed for {dependency['name']}: {error}"
            ) from error
        actual = digest.hexdigest()
        if actual != dependency["source_sha256"]:
            raise ValueError(
                f"download hash differs for {dependency['name']}: {actual}"
            )
        print(f"verify  {dependency['name']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument("--verify-downloads", action="store_true")
    args = parser.parse_args()
    document = load_and_validate()
    if args.verify_downloads:
        verify_downloads(document)
    content = canonical_bytes(build_spdx(document))
    if args.write:
        SBOM_PATH.parent.mkdir(parents=True, exist_ok=True)
        SBOM_PATH.write_bytes(content)
        print(f"write   {SBOM_PATH.relative_to(ROOT)}")
        return 0
    if not SBOM_PATH.exists() or SBOM_PATH.read_bytes() != content:
        print(f"stale   {SBOM_PATH.relative_to(ROOT)}", file=sys.stderr)
        return 1
    print(f"ok      {SBOM_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
