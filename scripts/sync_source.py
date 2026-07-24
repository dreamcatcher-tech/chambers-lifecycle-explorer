#!/usr/bin/env python3
"""Copy a committed Chambers lifecycle source from Fundamentals and rebuild the site data."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_REPO = ROOT.parent / "fundamentals"
SOURCE_RELATIVE_PATH = Path("docs/chambers-lifecycle-sequences.md")
DESTINATION = ROOT / "source" / "chambers-lifecycle-sequences.md"
METADATA = ROOT / "source" / "metadata.json"


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Copy the committed lifecycle sequence authority and regenerate Chambers Atlas data."
    )
    parser.add_argument(
        "source_repo",
        nargs="?",
        type=Path,
        default=DEFAULT_SOURCE_REPO,
        help=f"Fundamentals checkout (default: {DEFAULT_SOURCE_REPO})",
    )
    args = parser.parse_args(argv)
    source_repo = args.source_repo.resolve()
    source_file = source_repo / SOURCE_RELATIVE_PATH

    try:
        if not (source_repo / ".git").exists():
            raise RuntimeError(f"Not a Git checkout: {source_repo}")
        if not source_file.is_file():
            raise RuntimeError(f"Missing source: {source_file}")

        dirty = git(source_repo, "status", "--porcelain", "--", str(SOURCE_RELATIVE_PATH))
        if dirty:
            raise RuntimeError(
                "The lifecycle source has uncommitted changes. Commit it before copying so the public "
                "snapshot always has a verifiable source identity."
            )

        repository_head = git(source_repo, "rev-parse", "HEAD")
        source_commit = git(source_repo, "log", "-1", "--format=%H", "--", str(SOURCE_RELATIVE_PATH))
        source_commit_date = git(source_repo, "show", "-s", "--format=%cI", source_commit)
        remote_url = git(source_repo, "remote", "get-url", "origin")
        repository = remote_url.removesuffix(".git").split("github.com/")[-1]

        source_bytes = source_file.read_bytes()
        digest = hashlib.sha256(source_bytes).hexdigest()
        DESTINATION.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, DESTINATION)
        metadata = {
            "repository": repository,
            "path": str(SOURCE_RELATIVE_PATH),
            "repositoryHead": repository_head,
            "sourceCommit": source_commit,
            "sourceCommitDate": source_commit_date,
            "documentSha256": digest,
            "updateMode": "Committed source snapshot copied from the private Fundamentals repository",
        }
        METADATA.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_data.py"), "--print-summary"],
            cwd=ROOT,
            check=False,
        )
        if result.returncode:
            return result.returncode
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Synced {repository}@{source_commit[:12]} ({digest[:12]}…) into source/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
