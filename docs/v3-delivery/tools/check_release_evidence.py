"""Read-only evidence consistency check, NOT a product test or release authorization.

Python 3.11+, standard library only. This utility never connects to a service,
changes a repository, fills PASS entries, executes supplied commands, or publishes.
Records are untrusted claims until independently reviewed against their raw files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_CATALOG_SHA256 = "ddb675637f203fcf3aae6e409d2727d45110a7cd2e6519b23b97d20f9776e35a"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
SOURCE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".mdc", ".spec"}
REQUIRED_PROFILES = {
    "windows_native": {"os": "Windows", "real_target": True},
    "android_native": {"os": "Android", "physical_device": True},
    "ci": {"runner": "CI"},
    "build": {"os": "Windows", "packaged_app": True},
}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def owned_file(root: Path, relative: str) -> Path:
    """Reject traversal and external symlinks. Never accept a URL as a local file."""
    if not isinstance(relative, str) or not relative or "://" in relative:
        raise ValueError("expected nonempty relative evidence path")
    p = Path(relative)
    if p.is_absolute():
        raise ValueError("absolute paths are not accepted")
    result = (root / p).resolve()
    if not result.is_relative_to(root.resolve()) or not result.is_file():
        raise ValueError("file absent or outside evidence root")
    return result


def time_valid(raw: Any) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def junit_passed(path: Path, classname: str, name: str) -> bool:
    """Match one executed, non-skipped assertion container; no 'tests=0' success."""
    if not classname or not name or path.stat().st_size > 25 * 1024 * 1024:
        return False
    raw = path.read_bytes()
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        return False
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return False
    found = [t for t in root.iter("testcase")
             if t.get("classname") == classname and t.get("name") == name]
    return len(found) == 1 and not any(
        c.tag in {"failure", "error", "skipped"} for c in found[0]
    )


def validate(candidate: dict[str, Any], catalog: dict[str, Any],
             evidence_root: Path, expected_sha: str) -> list[str]:
    """Return all inconsistencies. Empty list means structure only, not real readiness."""
    errors: list[str] = []
    if not SHA40.fullmatch(expected_sha) or candidate.get("tested_commit") != expected_sha:
        errors.append("candidate: tested_commit must equal the explicitly selected full SHA")
    if candidate.get("schema_version") != 1:
        errors.append("candidate: schema_version must be 1")
    spec_cases = catalog.get("cases", [])
    rows = candidate.get("cases", [])
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        return errors + ["candidate: cases must be a list of objects"]
    ids = [r.get("id") for r in rows]
    required_ids = [r["id"] for r in spec_cases]
    if len(ids) != len(set(str(x) for x in ids)):
        errors.append("candidate: duplicate case IDs")
    if set(ids) != set(required_ids):
        errors.append("candidate: case IDs must exactly cover the frozen acceptance catalog")
    by_id = {r.get("id"): r for r in rows}

    artifact = candidate.get("artifact")
    artifact_hash = None
    if not isinstance(artifact, dict):
        errors.append("artifact: candidate archive metadata missing")
    else:
        try:
            p = owned_file(evidence_root, artifact.get("path", ""))
            artifact_hash = digest(p)
            if p.suffix.lower() not in {".zip", ".exe", ".msi", ".7z"}:
                errors.append("artifact: expected an actual candidate archive or Windows binary")
            if p.stat().st_size == 0 or artifact_hash != artifact.get("sha256"):
                errors.append("artifact: empty file or SHA256 mismatch")
        except (ValueError, OSError) as exc:
            errors.append(f"artifact: {exc}")
        if artifact.get("built_from") != expected_sha:
            errors.append("artifact: built_from differs from selected commit")

    for spec in spec_cases:
        cid = spec["id"]
        row = by_id.get(cid)
        if not row:
            continue
        if row.get("status") != "PASS":
            errors.append(f"{cid}: {row.get('status', 'MISSING')} cannot close required acceptance")
            continue
        receipts = row.get("receipts")
        if not isinstance(receipts, list) or not receipts:
            errors.append(f"{cid}: PASS without receipts")
            continue
        kinds = {r.get("kind") for r in receipts if isinstance(r, dict)}
        if not set(spec["required_kinds"]).issubset(kinds):
            errors.append(f"{cid}: missing evidence kinds {spec['required_kinds']}")
        for n, receipt in enumerate(receipts):
            label = f"{cid}/receipt[{n}]"
            if not isinstance(receipt, dict):
                errors.append(label + ": not an object")
                continue
            kind = receipt.get("kind")
            if kind not in {"automated", "windows_native", "android_native", "ci", "build", "review", "static_review"}:
                errors.append(label + ": unknown evidence kind")
            if receipt.get("tested_commit") != expected_sha:
                errors.append(label + ": stale/missing tested_commit")
            for field in ("observed", "expected", "executor"):
                if not isinstance(receipt.get(field), str) or not receipt[field].strip():
                    errors.append(label + f": missing {field}")
            if not time_valid(receipt.get("executed_at")):
                errors.append(label + ": executed_at requires ISO timestamp with timezone")
            if kind in {"automated", "ci", "build"}:
                if type(receipt.get("exit_code")) is not int or receipt["exit_code"] != 0:
                    errors.append(label + ": missing/nonzero command exit code")
                if not isinstance(receipt.get("command"), str) or not receipt["command"].strip():
                    errors.append(label + ": missing executed command")
            profile = receipt.get("environment")
            if not isinstance(profile, dict):
                errors.append(label + ": missing environment object")
                profile = {}
            if not profile.get("version"):
                errors.append(label + ": environment version missing")
            for key, val in REQUIRED_PROFILES.get(str(kind), {}).items():
                if profile.get(key) != val:
                    errors.append(label + f": environment {key} must be {val!r}")
            if kind in {"windows_native", "android_native", "build"}:
                if not artifact_hash or receipt.get("artifact_sha256") != artifact_hash:
                    errors.append(label + ": native/build proof not bound to candidate archive hash")
            checked: dict[str, Path] = {}
            files = receipt.get("files")
            if not isinstance(files, list) or not files:
                errors.append(label + ": raw evidence files missing")
                files = []
            for f in files:
                try:
                    if not isinstance(f, dict):
                        raise ValueError("file descriptor must be an object")
                    path = owned_file(evidence_root, f.get("path", ""))
                    if not SHA64.fullmatch(str(f.get("sha256", ""))) or digest(path) != f.get("sha256"):
                        raise ValueError("evidence SHA256 mismatch")
                    if path.stat().st_size == 0:
                        raise ValueError("empty evidence file")
                    if kind not in {"static_review", "review"} and path.suffix.lower() in SOURCE_SUFFIXES:
                        raise ValueError("source file is not runtime evidence")
                    checked[f["path"]] = path
                except (ValueError, OSError) as exc:
                    errors.append(label + f": {exc}")
            if kind in {"automated", "ci"}:
                j = receipt.get("junit", {})
                if not isinstance(j, dict):
                    j = {}
                path = checked.get(j.get("path", ""))
                if path is None or not junit_passed(path, j.get("classname", ""), j.get("name", "")):
                    errors.append(label + ": missing executed non-skipped JUnit testcase")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--catalog", type=Path, default=ROOT / "acceptance_catalog.json")
    args = parser.parse_args()
    try:
        if digest(args.catalog) != EXPECTED_CATALOG_SHA256:
            raise ValueError("frozen catalog changed: independent scope review required")
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be a JSON object")
        errors = validate(candidate, catalog, args.evidence_root, args.expected_sha)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "INVALID_INPUT", "error": str(exc), "release_authorized": False}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "status": "REJECTED" if errors else "EVIDENCE_STRUCTURE_OK_REQUIRES_INDEPENDENT_REVIEW",
        "errors": errors,
        "product_verified_by_this_tool": False,
        "release_authorized": False,
    }, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
