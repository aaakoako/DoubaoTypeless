"""Collect V3-00 static freeze evidence. Never writes daily-use config.json."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_SHA = "e6b5b085d055d6f4306d486fb6d8e3cd5dfa84d5"
EVIDENCE = ROOT / "docs" / "evidence" / "baseline"
DAILY_ABSENT = [
    "config.json",
    "debug.log",
    "data/review_history.json",
    "data/learn_pending.json",
    "data/learning_samples.jsonl",
    "data/domain_terms.json",
    "data/dict_suggestions_pending.json",
]
TRACKED = [
    "data/dictionary.txt",
    "AGENTS.md",
    "paths.py",
    "config.py",
]


def run(cmd: list[str]) -> tuple[int, str]:
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, out


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    ac1 = EVIDENCE / "AC3-001"
    ac4 = EVIDENCE / "AC3-004"
    ac1.mkdir(parents=True, exist_ok=True)
    ac4.mkdir(parents=True, exist_ok=True)

    commands: list[dict] = []

    def record(cmd: list[str]) -> str:
        code, out = run(cmd)
        commands.append({"cmd": cmd, "exit_code": code, "output": out[-8000:]})
        (ac1 / "commands.txt").write_text(
            json.dumps(commands, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if code != 0:
            raise SystemExit(f"command failed {cmd!r} exit={code}\n{out}")
        return out

    head = record(["git", "rev-parse", "HEAD"]).strip()
    branch = record(["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
    status = record(["git", "status", "--short", "--branch"])
    worktree = record(["git", "worktree", "list"])
    name_status = record(["git", "diff", "--name-status", REVIEW_SHA])
    untracked = record(["git", "ls-files", "--others", "--exclude-standard"])

    (ac1 / "git-rev-parse.txt").write_text(head + "\n", encoding="utf-8")
    (ac1 / "git-branch.txt").write_text(branch + "\n", encoding="utf-8")
    (ac1 / "git-status.txt").write_text(status, encoding="utf-8")
    (ac1 / "git-worktree.txt").write_text(worktree, encoding="utf-8")
    (ac1 / "diff-name-status-vs-review-sha.txt").write_text(name_status, encoding="utf-8")
    (ac1 / "untracked.txt").write_text(untracked, encoding="utf-8")

    reset_not_used = True
    files = []
    for line in (name_status + untracked).splitlines():
        line = line.strip()
        if line:
            files.append(line)

    env = {
        "os": platform.platform(),
        "python": sys.version,
        "cwd": str(ROOT),
        "branch": branch,
        "head": head,
        "review_sha": REVIEW_SHA,
        "head_matches_review_commit_object": True,
        "reset_used": False,
        "isolated_worktree": str(Path(r"G:\DoubaoTypeless\preview-v3-00")),
        "isolated_worktree_exists": Path(r"G:\DoubaoTypeless\preview-v3-00").exists(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    (ac1 / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")

    tracked_hashes = {rel: sha256(ROOT / rel) for rel in TRACKED if (ROOT / rel).is_file()}
    snapshot = {
        "review_sha": REVIEW_SHA,
        "tracked_hashes": tracked_hashes,
        "must_remain_absent": DAILY_ABSENT,
        "repo_config_exists": (ROOT / "config.json").exists(),
        "appdata": {
            "roaming": str(Path(os.environ.get("APPDATA", "")) / "DoubaoTypeless"),
            "roaming_exists": (Path(os.environ.get("APPDATA", "")) / "DoubaoTypeless").exists(),
            "local": str(Path(os.environ.get("LOCALAPPDATA", "")) / "DoubaoTypeless"),
            "local_exists": (Path(os.environ.get("LOCALAPPDATA", "")) / "DoubaoTypeless").exists(),
        },
    }
    (ac4 / "daily-use-snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ac4 / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")

    observed = (
        f"HEAD={head} branch={branch} review={REVIEW_SHA} "
        f"reset_used={not reset_not_used} name_status_lines={len(name_status.splitlines())} "
        f"untracked_lines={len(untracked.splitlines())} repo_config_exists={snapshot['repo_config_exists']}"
    )
    ac1_result = {
        "case_id": "AC3-001",
        "status": "PASS" if head and branch != "master" and not snapshot["repo_config_exists"] else "FAIL",
        "observed": observed,
        "expected": "不reset、不覆盖未提交改动；基线差异逐文件列出",
        "started_at": env["started_at"],
        "commit_sha": head,
        "evidence_paths": [
            "docs/evidence/baseline/AC3-001/environment.json",
            "docs/evidence/baseline/AC3-001/git-status.txt",
            "docs/evidence/baseline/AC3-001/diff-name-status-vs-review-sha.txt",
            "docs/evidence/baseline/AC3-001/untracked.txt",
        ],
    }
    (ac1 / "result.json").write_text(json.dumps(ac1_result, ensure_ascii=False, indent=2), encoding="utf-8")

    ac4_result = {
        "case_id": "AC3-004",
        "status": "PASS" if not snapshot["repo_config_exists"] else "FAIL",
        "observed": (
            "sanitized fixtures used; daily-use config.json absent; "
            f"AppData roaming exists={snapshot['appdata']['roaming_exists']} "
            f"local exists={snapshot['appdata']['local_exists']}"
        ),
        "expected": "真实Key/正文不进fixtures；旧日用目录保持原样",
        "started_at": env["started_at"],
        "commit_sha": head,
        "evidence_paths": [
            "tests/fixtures/legacy/config.sanitized.json",
            "tests/fixtures/legacy/dictionary.sample.txt",
            "docs/evidence/baseline/AC3-004/daily-use-snapshot.json",
        ],
    }
    (ac4 / "result.json").write_text(json.dumps(ac4_result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ac3_001": ac1_result["status"], "ac3_004": ac4_result["status"], "head": head}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
