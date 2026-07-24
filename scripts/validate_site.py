#!/usr/bin/env python3
"""Fail-closed validation for the static multi-document Lifecycle Atlas publication."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SOURCE = ROOT / "source"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_bundle() -> dict:
    path = SITE / "data.js"
    text = path.read_text(encoding="utf-8")
    marker = "window.LIFECYCLE_ATLAS_DATA = "
    marker_index = text.find(marker)
    if marker_index < 0 or not text.rstrip().endswith(";"):
        fail("data.js is not the expected Lifecycle Atlas assignment")
    return json.loads(text[marker_index + len(marker) :].rstrip()[:-1])


def validate_required_files() -> None:
    required = [
        SITE / "index.html",
        SITE / "styles.css",
        SITE / "app.js",
        SITE / "data.js",
        SITE / "favicon.svg",
        SITE / ".nojekyll",
        SOURCE / "manifest.json",
        SOURCE / "chambers-lifecycle-sequences.md",
        SOURCE / "cardflow-filesystem-lease-sequences.md",
        ROOT / ".github" / "workflows" / "pages.yml",
        ROOT / "scripts" / "sync_source.py",
        ROOT / "scripts" / "build_data.py",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")
    if (SOURCE / "metadata.json").exists():
        fail("legacy source/metadata.json remains; manifest.json is the only authority")


def validate_manifest_and_bundle(payload: dict) -> None:
    manifest = json.loads((SOURCE / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 2:
        fail("source manifest schemaVersion must be 2")
    if payload.get("schemaVersion") != 2:
        fail("browser bundle schemaVersion must be 2")
    if payload.get("defaultDocumentId") != "chambers":
        fail("default document must remain Chambers")

    documents = payload.get("documents", [])
    if [document.get("id") for document in documents] != ["chambers", "cardflow"]:
        fail("bundle must contain Chambers and Cardflow in that order")
    if payload.get("stats") != {"documents": 2, "sequences": 18, "calls": 146, "functions": 70}:
        fail(f"unexpected combined stats: {payload.get('stats')}")

    manifest_by_id = {entry["id"]: entry for entry in manifest.get("documents", [])}
    for document in documents:
        source = document.get("source", {})
        entry = manifest_by_id.get(document["id"])
        if not entry:
            fail(f"manifest is missing {document['id']}")
        snapshot = SOURCE / entry["snapshotPath"]
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        if digest != entry.get("documentSha256") or digest != source.get("documentSha256"):
            fail(f"{document['id']} source hash binding failed")
        expected_url = f"https://github.com/{manifest['repository']}/blob/{entry['sourceCommit']}/{entry['path']}"
        if source.get("url") != expected_url:
            fail(f"{document['id']} exact source URL is wrong")
        if not document.get("sequences") or not document.get("functions"):
            fail(f"{document['id']} has no generated sequence/function content")
        if any(call["function"] not in {fn["id"] for fn in document["functions"]} for sequence in document["sequences"] for call in sequence["calls"]):
            fail(f"{document['id']} contains an unresolved call")

    chambers, cardflow = documents
    if chambers["stats"] != {"sequences": 9, "actors": 34, "calls": 80, "i3Calls": 63, "hostCalls": 17, "functions": 37, "usedFunctions": 36}:
        fail(f"unexpected Chambers stats: {chambers['stats']}")
    if cardflow["stats"] != {"sequences": 9, "actors": 19, "calls": 66, "i3Calls": 66, "hostCalls": 0, "functions": 33, "usedFunctions": 31}:
        fail(f"unexpected Cardflow stats: {cardflow['stats']}")


def validate_html_and_assets(payload: dict) -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    css = (SITE / "styles.css").read_text(encoding="utf-8")
    app = (SITE / "app.js").read_text(encoding="utf-8")

    required_ids = {
        "documentSwitcher", "mobileDocumentSelect", "mobileSceneSelect", "journeyList",
        "sourceDocumentLink", "footerSource", "sequenceViewport", "sequenceSvg",
        "playPause", "stepScrubber", "mapViewport", "mapSvg", "functionList",
        "functionDetail", "searchDialog", "helpDialog",
    }
    ids = re.findall(r'\bid="([^"]+)"', html)
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        fail(f"duplicate HTML ids: {', '.join(duplicates)}")
    missing_ids = sorted(required_ids - set(ids))
    if missing_ids:
        fail(f"missing interactive ids: {', '.join(missing_ids)}")

    for element_id in ("sourceDocumentLink", "footerSource"):
        pattern = rf'<a[^>]*id="{element_id}"[^>]*target="_blank"[^>]*rel="noopener noreferrer"'
        if not re.search(pattern, html):
            fail(f"{element_id} must open the exact private source in a safe new page")

    if "window.LIFECYCLE_ATLAS_DATA" not in app or "state.documentId" not in app or "data-document-id" not in app:
        fail("app.js does not implement document-aware state/navigation")
    if "window.CHAMBERS_DATA" in app or "scrollCallIntoView" in app:
        fail("legacy single-document or auto-focus scrolling code remains")
    if "viewportPosition" not in app:
        fail("sequence selection no longer explicitly preserves viewport position")
    if ".document-switcher" not in css or "body[data-document=\"cardflow\"]" not in css:
        fail("document workspace styling is missing")

    local_refs = re.findall(r'(?:src|href)="([^"]+)"', html)
    for ref in local_refs:
        parsed = urlparse(ref)
        if parsed.scheme or ref.startswith("#"):
            continue
        target = SITE / parsed.path
        if not target.exists():
            fail(f"HTML references missing asset {ref}")

    if re.search(r'https?://', html):
        fail("site shell contains a remote runtime or asset dependency")
    if any(path.name.startswith("qa") for path in SITE.iterdir()):
        fail("QA artifacts leaked into site/")

    source_urls = {document["source"]["url"] for document in payload["documents"]}
    if len(source_urls) != 2 or not all(url.startswith("https://github.com/") for url in source_urls):
        fail("generated exact-source URL registry is incomplete")


def validate_documented_deep_links(payload: dict) -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    examples = re.findall(r"^\?([^\s`]+)$", text, flags=re.MULTILINE)
    if len(examples) < 4:
        fail("README must retain document-aware deep-link examples")
    documents = {document["id"]: document for document in payload["documents"]}
    for example in examples:
        params = parse_qs(example)
        document_id = params.get("doc", [payload["defaultDocumentId"]])[0]
        document = documents.get(document_id)
        if not document:
            fail(f"README deep link names unknown document {document_id!r}")
        sequences = {sequence["id"]: sequence for sequence in document["sequences"]}
        functions = {function["id"] for function in document["functions"]}
        diagram_id = params.get("diagram", [document["sequences"][0]["id"]])[0]
        if diagram_id not in sequences:
            fail(f"README deep link names unknown {document_id} diagram {diagram_id!r}")
        function_id = params.get("function", [None])[0]
        if function_id and function_id not in functions:
            fail(f"README deep link names unknown {document_id} function {function_id!r}")
        call_id = params.get("call", [None])[0]
        if call_id and call_id not in {call["id"] for call in sequences[diagram_id]["calls"]}:
            fail(f"README deep link names unknown {document_id}/{diagram_id} call {call_id!r}")


def run_build_check() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_data.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        fail("generated data does not match the authoritative snapshots")


def main() -> None:
    validate_required_files()
    run_build_check()
    payload = load_bundle()
    validate_manifest_and_bundle(payload)
    validate_html_and_assets(payload)
    validate_documented_deep_links(payload)
    print("PASS: two exact source snapshots, generated data, app shell, navigation, and publication assets are valid")


if __name__ == "__main__":
    main()
