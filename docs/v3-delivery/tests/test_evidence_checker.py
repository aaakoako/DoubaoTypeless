"""Synthetic tests of the checker itself; NEVER V3 product acceptance results."""
from __future__ import annotations
import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("checker", ROOT / "tools/check_release_evidence.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
SHA = "a" * 40


class EvidenceCheckerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "candidate.zip").write_bytes(b"synthetic checker fixture; not a product package")
        (self.root / "run.xml").write_text('<testsuite><testcase classname="tests.flow" name="check"/></testsuite>')
        (self.root / "record.txt").write_text("Synthetic observation, checker unit test only")
        self.archive_hash = checker.digest(self.root / "candidate.zip")
        self.receipt = {
            "kind": "automated", "tested_commit": SHA,
            "executed_at": "2026-09-18T10:00:00+00:00", "executor": "unit-fixture",
            "observed": "fixture", "expected": "fixture", "command": "synthetic", "exit_code": 0,
            "environment": {"version": "fixture"},
            "files": [{"path": "run.xml", "sha256": checker.digest(self.root / "run.xml")}],
            "junit": {"path": "run.xml", "classname": "tests.flow", "name": "check"},
        }
        self.catalog = {"cases": [{"id": "AC-TEST", "required_kinds": ["automated"]}]}
        self.candidate = {
            "schema_version": 1, "tested_commit": SHA,
            "artifact": {"path": "candidate.zip", "sha256": self.archive_hash, "built_from": SHA},
            "cases": [{"id": "AC-TEST", "status": "PASS", "receipts": [self.receipt]}],
        }

    def check(self):
        return checker.validate(self.candidate, self.catalog, self.root, SHA)

    def test_valid_fixture_only_checks_structure(self):
        self.assertEqual(self.check(), [])

    def test_pass_without_receipt_rejected(self):
        self.candidate["cases"][0]["receipts"] = []
        self.assertTrue(self.check())

    def test_stale_commit_rejected(self):
        self.receipt["tested_commit"] = "b" * 40
        self.assertTrue(self.check())

    def test_source_file_not_runtime_evidence(self):
        (self.root / "source.py").write_text("assert True")
        self.receipt["files"] = [{"path": "source.py", "sha256": checker.digest(self.root / "source.py")}]
        self.assertTrue(self.check())

    def test_changed_file_rejected(self):
        (self.root / "run.xml").write_text("changed")
        self.assertTrue(self.check())

    def test_missing_file_rejected(self):
        (self.root / "run.xml").unlink()
        self.assertTrue(self.check())

    def test_skipped_test_rejected(self):
        (self.root / "run.xml").write_text('<testsuite><testcase classname="tests.flow" name="check"><skipped/></testcase></testsuite>')
        self.receipt["files"][0]["sha256"] = checker.digest(self.root / "run.xml")
        self.assertTrue(self.check())

    def test_zero_test_suite_rejected(self):
        (self.root / "run.xml").write_text('<testsuite tests="0"/>')
        self.receipt["files"][0]["sha256"] = checker.digest(self.root / "run.xml")
        self.assertTrue(self.check())

    def test_nonzero_exit_rejected(self):
        self.receipt["exit_code"] = 2
        self.assertTrue(self.check())

    def test_missing_case_rejected(self):
        self.candidate["cases"] = []
        self.assertTrue(self.check())

    def test_duplicate_case_rejected(self):
        self.candidate["cases"].append(copy.deepcopy(self.candidate["cases"][0]))
        self.assertTrue(self.check())

    def test_wrong_evidence_layer_rejected(self):
        self.catalog["cases"][0]["required_kinds"] = ["windows_native"]
        self.assertTrue(self.check())

    def test_blocked_not_ready(self):
        self.candidate["cases"][0]["status"] = "BLOCKED_NATIVE"
        self.assertTrue(self.check())

    def test_changed_artifact_rejected(self):
        (self.root / "candidate.zip").write_bytes(b"different")
        self.assertTrue(self.check())

    def test_path_escape_rejected(self):
        self.receipt["files"][0]["path"] = "../anything.xml"
        self.assertTrue(self.check())

    def test_naive_timestamp_rejected(self):
        self.receipt["executed_at"] = "2026-09-18T10:00:00"
        self.assertTrue(self.check())

    def test_simulated_android_not_native(self):
        self.catalog["cases"][0]["required_kinds"] = ["android_native"]
        self.receipt.update(kind="android_native", artifact_sha256=self.archive_hash,
                            environment={"os": "Android", "version": "fixture", "physical_device": False})
        self.assertTrue(self.check())

    def test_native_hash_must_match_candidate(self):
        self.catalog["cases"][0]["required_kinds"] = ["windows_native"]
        self.receipt.update(kind="windows_native", artifact_sha256="b" * 64,
                            environment={"os": "Windows", "version": "fixture", "real_target": True})
        self.assertTrue(self.check())


if __name__ == "__main__":
    unittest.main(verbosity=2)
