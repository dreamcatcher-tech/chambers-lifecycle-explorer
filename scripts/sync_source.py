#!/usr/bin/env python3
"""Copy exact registered sequence sources and rebuild the public projection."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"
MANIFEST_PATH = SOURCE_DIR / "manifest.json"
LEGACY_METADATA_PATH = SOURCE_DIR / "metadata.json"
DOCUMENTS = (
    {
        "id": "chambers",
        "path": "docs/chambers-lifecycle-sequences.md",
        "snapshotPath": "chambers-lifecycle-sequences.md",
        "role": "downstream_projection_of_chambers_formal_specification",
    },
    {
        "id": "cardflow",
        "path": "docs/cardflow-filesystem-lease-sequences.md",
        "snapshotPath": "cardflow-filesystem-lease-sequences.md",
        "role": "cardflow_design_source_with_chambers_formal_release_binding",
    },
)


def run(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def repository_slug(remote_url: str) -> str:
    cleaned = remote_url.strip()
    match = re.search(r"github\.com(?::|/)([^/]+/[^/]+?)(?:\.git)?$", cleaned)
    if not match:
        raise ValueError(f"Cannot derive GitHub repository from origin URL: {remote_url!r}")
    return match.group(1)


def assert_safe_source_repo(repo: Path) -> None:
    if not (repo / ".git").exists():
        raise ValueError(f"Not a Git repository: {repo}")
    dirty = run(repo, "status", "--short")
    if dirty:
        raise ValueError(
            "Fundamentals has local changes. Refusing to project ambiguous source bytes:\n" + dirty
        )
    branch = run(repo, "branch", "--show-current")
    if not branch:
        raise ValueError("Fundamentals is detached; sync an explicit branch before projection")
    upstream = run(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    ahead_behind = run(repo, "rev-list", "--left-right", "--count", f"{upstream}...HEAD")
    behind, ahead = (int(value) for value in ahead_behind.split())
    if behind or ahead:
        raise ValueError(
            f"Fundamentals must exactly match {upstream}; behind={behind}, ahead={ahead}"
        )


def source_entry(repo: Path, document: dict[str, str]) -> tuple[dict[str, object], Path]:
    source_path = repo / document["path"]
    if not source_path.exists():
        raise FileNotFoundError(f"Missing registered source document: {source_path}")
    tracked = run(repo, "ls-files", "--error-unmatch", document["path"])
    if tracked != document["path"]:
        raise ValueError(f"Source document is not tracked exactly: {document['path']}")
    source_bytes = source_path.read_bytes()
    source_commit = run(repo, "log", "-1", "--format=%H", "--", document["path"])
    source_timestamp = run(repo, "log", "-1", "--format=%cI", "--", document["path"])
    return (
        {
            "id": document["id"],
            "role": document["role"],
            "path": document["path"],
            "snapshotPath": document["snapshotPath"],
            "sourceCommit": source_commit,
            "sourceTimestamp": source_timestamp,
            "documentSha256": hashlib.sha256(source_bytes).hexdigest(),
            "documentBytes": len(source_bytes),
        },
        source_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fundamentals_repo",
        nargs="?",
        default="../fundamentals",
        help="Path to a clean, synchronized Fundamentals checkout",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Only copy sources and rebuild data; do not run tests or static validation",
    )
    args = parser.parse_args(argv)

    repo = Path(args.fundamentals_repo).resolve()
    try:
        assert_safe_source_repo(repo)
        remote_url = run(repo, "remote", "get-url", "origin")
        repository = repository_slug(remote_url)
        repository_head = run(repo, "rev-parse", "HEAD")
        repository_head_timestamp = run(repo, "show", "-s", "--format=%cI", "HEAD")
        binding = json.loads(
            (repo / "docs" / "chambers-formal-specification.json").read_text(encoding="utf-8")
        )
        formal_authority = binding["authority_source"]
        entries_and_paths = [source_entry(repo, document) for document in DOCUMENTS]
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        detail = exc.stderr.strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        print(f"ERROR: {detail}", file=sys.stderr)
        return 1

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    for entry, source_path in entries_and_paths:
        shutil.copyfile(source_path, SOURCE_DIR / str(entry["snapshotPath"]))

    manifest = {
        "schemaVersion": 3,
        "repository": repository,
        "repositoryHead": repository_head,
        "repositoryHeadTimestamp": repository_head_timestamp,
        "projectionMode": "exact committed registered-source snapshots; generated browser data",
        "formalAuthority": formal_authority,
        "documents": [entry for entry, _ in entries_and_paths],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if LEGACY_METADATA_PATH.exists():
        LEGACY_METADATA_PATH.unlink()

    commands = [[sys.executable, str(ROOT / "scripts" / "build_data.py")]]
    if not args.skip_validation:
        commands.extend(
            [
                [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests"), "-v"],
                [sys.executable, str(ROOT / "scripts" / "build_data.py"), "--check", "--print-summary"],
                [sys.executable, str(ROOT / "scripts" / "validate_site.py")],
            ]
        )
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT)
        if completed.returncode:
            return completed.returncode

    print(
        f"Synced {len(DOCUMENTS)} registered sources from {repository}@{repository_head[:12]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
