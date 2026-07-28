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
RUNBOOK = ROOT / "docs" / "source-refresh-runbook.md"


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
        ROOT / "AGENTS.md",
        RUNBOOK,
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
    if payload.get("stats") != {"documents": 2, "sequences": 22, "calls": 238, "functions": 83, "dictionaryTerms": 83}:
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
        if not document.get("sequences") or not document.get("functions") or not document.get("dictionary"):
            fail(f"{document['id']} has no generated sequence/function/dictionary content")
        if any(call["function"] not in {fn["id"] for fn in document["functions"]} for sequence in document["sequences"] for call in sequence["calls"]):
            fail(f"{document['id']} contains an unresolved call")
        dictionary_ids = {term["id"] for term in document["dictionary"]}
        if len(dictionary_ids) != len(document["dictionary"]):
            fail(f"{document['id']} contains duplicate dictionary ids")
        if any(related not in dictionary_ids for term in document["dictionary"] for related in term["related"]):
            fail(f"{document['id']} contains an unresolved related dictionary term")
        source_lines = snapshot.read_text(encoding="utf-8").splitlines()
        if any(
            not source_lines[term["sourceLine"] - 1].startswith(f"| {term['term']} |")
            for term in document["dictionary"]
        ):
            fail(f"{document['id']} dictionary source-line binding failed")

    chambers, cardflow = documents
    if chambers["stats"] != {"sequences": 13, "actors": 34, "calls": 172, "i3Calls": 121, "hostCalls": 51, "functions": 50, "usedFunctions": 49, "dictionaryTerms": 53}:
        fail(f"unexpected Chambers stats: {chambers['stats']}")
    if cardflow["stats"] != {"sequences": 9, "actors": 19, "calls": 66, "i3Calls": 66, "hostCalls": 0, "functions": 33, "usedFunctions": 31, "dictionaryTerms": 30}:
        fail(f"unexpected Cardflow stats: {cardflow['stats']}")

    expected_startup = ["core-installation", "host-activation", "core-bootstrap", "core-reboot", "activation-kernel"]
    if [sequence["id"] for sequence in chambers["sequences"][:5]] != expected_startup:
        fail("Chambers must present first boot install, selected Boot-set cold start, boot control bootstrap, selected-Boot-set reboot, then ordinary activation")
    for sequence in chambers["sequences"]:
        participants = [participant["id"] for participant in sequence["participants"]]
        if "HostAgent" in participants and participants[0] != "HostAgent":
            fail(f"{sequence['id']} does not keep Host Agent leftmost")
        if any(item in participants for item in ("procman", "Materializer", "Runtime")):
            fail(f"{sequence['id']} retains a removed Chambers host lane")
        for call in sequence["calls"]:
            if call["to"] == "containerd" and (
                call["from"] != "HostAgent" or not call["function"].startswith("containerd_")
            ):
                fail(f"{sequence['id']} bypasses the Host Agent containerd boundary")
            if call["from"] == "containerd":
                fail(f"{sequence['id']} lets containerd initiate lifecycle work")
            if call["function"] in {
                "chamber::activate", "chamber::inspect", "chamber::stop",
                "bootset::stage", "bootset::inspect", "bootset::select", "bootset::quiesce",
            } and call["to"] != "HostAgent":
                fail(f"{sequence['id']} aims a Host Agent I3 function at {call['to']}")

    sequence_by_id = {sequence["id"]: sequence for sequence in chambers["sequences"]}
    host_activation = sequence_by_id["host-activation"]
    host_calls = [call["function"] for call in host_activation["calls"]]
    if "engine::identity::attest" in host_calls or host_calls.count("containerd_task_start") != 4:
        fail("selected Boot-set cold start must have four ordered conditional starts and no identity-attest call")
    activations = [call for call in host_activation["calls"] if call["function"] == "containerd_task_start"]
    activation_labels = {context["label"] for call in activations for context in call["context"]}
    expected_activation_labels = {
        "No matching ready Engine task exists",
        "No matching ready Router task exists",
        "No matching ready Persistence task exists",
        "No matching ready Supervisor task exists",
    }
    if not expected_activation_labels <= activation_labels:
        fail("cold-start task starts must retain separate ordered no-matching boot-member branches")

    all_calls = [call for sequence in chambers["sequences"] for call in sequence["calls"]]
    if any(call["from"] == "containerd" for call in all_calls):
        fail("containerd must not initiate lifecycle, Persistence, or I3 calls")
    if any({call["from"], call["to"]} == {"containerd", "Persistence"} for call in all_calls):
        fail("containerd and Persistence must remain separated by the Host Agent boundary")
    for call in all_calls:
        if call["to"] == "Engine":
            fail("Engine must not own a Dreamcatcher lifecycle function")
        if call["from"] == "Engine" and not (
            call["to"] == "Router"
            and call["function"] in {"routing::authenticate", "routing::authorize_registration"}
        ):
            fail("Engine may invoke only the fixed Router authentication and registration hooks")
        if call["function"].startswith("routing::") and call["to"] not in {"Router", "NextRouter"}:
            fail("every routing function must target the selected or candidate Router Covenant")
        if call["from"] == "HostAgent" and call["function"] in {
            "routing::reconcile", "routing::fence", "routing::install", "routing::reopen", "routing::claim",
        }:
            fail("Host Agent must not mutate Router state")
    persistence_roles = {
        participant["role"]
        for sequence in chambers["sequences"]
        for participant in sequence["participants"]
        if participant["id"] == "Persistence"
    }
    if persistence_roles != {"resource"}:
        fail(f"Persistence must remain a resource actor, got {persistence_roles}")

    chambers_snapshot = (SOURCE / chambers["source"]["snapshotPath"]).read_text(encoding="utf-8")
    required_boot_markers = (
        "dreamcatcher/bootset:current",
        "Selection uses one image-record mutation over the coherent quartet",
        "Bootstrap Engine Covenant",
        "Router Covenant",
        "Persistence Covenant",
        "Supervisor Covenant",
        "Router and Supervisor are the mutual live-upgrade pair",
        "operation-bound retention receipt + successor-scoped Admission renewal",
        "protected Router control listener",
        "one mechanism-only Host Agent replacing separate Procman, Image Materializer, and direct-runsc adapter roles",
        "Builder remains outside every boot Chamber",
    )
    missing_boot_markers = [marker for marker in required_boot_markers if marker not in chambers_snapshot]
    if missing_boot_markers:
        fail(f"Chambers boot authority contract is incomplete: {missing_boot_markers}")
    reboot = sequence_by_id["core-reboot"]
    reboot_calls = [call["function"] for call in reboot["calls"]]
    if reboot_calls.count("containerd_task_start") != 4 or "containerd_import" in reboot_calls:
        fail("selected-Boot-set reboot must start four retained members in dependency order")
    selection = sequence_by_id["selection-rollback"]
    selection_calls = [call["function"] for call in selection["calls"]]
    if selection_calls.index("bootset::stage") >= selection_calls.index("bootset::select"):
        fail("Boot-set closure must be staged before Host Agent selection")
    if "containerd_tag_update" not in selection_calls:
        fail("Boot-set selection must expose the one Host Agent containerd tag update")
    cutover_calls = [call["function"] for call in sequence_by_id["core-cutover"]["calls"]]
    if cutover_calls.count("containerd_task_start") != 12 or cutover_calls.count("containerd_tag_update") != 4:
        fail("live Boot-set cutover must preserve Supervisor-, Router-, Persistence-, and Engine-changing branches")
    if "routing::claim" not in cutover_calls or "persistence::routing::prepare" not in cutover_calls:
        fail("live Boot-set cutover must preserve durable handover preparation and Router claim")
    supervisor_branch = "Same Engine and only Supervisor changes"
    if not any(
        call["function"] == "routing::reconcile"
        and call["from"] == "NextSupervisor"
        and supervisor_branch in {context["branch"] for context in call["context"]}
        for call in sequence_by_id["core-cutover"]["calls"]
    ):
        fail("successor Supervisor must consume the prepared handover through the current Router")
    if cutover_calls.index("containerd_tag_update") >= cutover_calls.index("routing::inspect"):
        fail("live Boot-set cutover must prove successor routing only after the selection decision")


def validate_html_and_assets(payload: dict) -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    css = (SITE / "styles.css").read_text(encoding="utf-8")
    app = (SITE / "app.js").read_text(encoding="utf-8")

    required_ids = {
        "documentSwitcher", "mobileDocumentSelect", "mobileSceneSelect", "journeyList",
        "sourceDocumentLink", "footerSource", "stickyActorHeader", "stickyActorSvg", "sequenceViewport", "sequenceSvg",
        "resetSequence", "playPause", "stepScrubber", "mapViewport", "mapSvg", "functionList",
        "functionDetail", "dictionaryView", "dictionarySearch", "dictionaryList", "dictionaryDetail",
        "searchDialog", "helpDialog",
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
        fail("legacy single-document or disruptive canvas auto-focus code remains")
    interaction_markers = [
        "horizontalPosition",
        "scheduleVerticalCallReveal",
        "syncStickyActorHeader",
        "scheduleHistoryScrollSnapshot",
        "reconcileFilteredCallSelection",
        "sequenceFocusIdentity",
        'window.history.scrollRestoration = "manual"',
        "event.defaultPrevented",
        'overflow-y: clip',
        'overflow-anchor: none',
        'call-function-meta',
        'id="resetSequence"',
        'window.history.pushState',
        'window.addEventListener("popstate"',
        'data-view="dictionary"',
        "renderDictionaryCatalog",
        "dictionary-source-link",
    ]
    missing_interaction_markers = [marker for marker in interaction_markers if marker not in html + css + app]
    if missing_interaction_markers:
        fail(f"trace interaction/history contract is incomplete: {missing_interaction_markers}")
    if 'id="currentBranch"' in html or "branch-chip" in app:
        fail("the stable selected-call summary must not duplicate wrapping branch context")
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
        assert document is not None
        sequences = {sequence["id"]: sequence for sequence in document["sequences"]}
        functions = {function["id"] for function in document["functions"]}
        dictionary = {term["id"] for term in document["dictionary"]}
        diagram_id = params.get("diagram", [document["sequences"][0]["id"]])[0]
        if diagram_id not in sequences:
            fail(f"README deep link names unknown {document_id} diagram {diagram_id!r}")
        function_id = params.get("function", [None])[0]
        if function_id and function_id not in functions:
            fail(f"README deep link names unknown {document_id} function {function_id!r}")
        term_id = params.get("term", [None])[0]
        if term_id and term_id not in dictionary:
            fail(f"README deep link names unknown {document_id} dictionary term {term_id!r}")
        call_id = params.get("call", [None])[0]
        if call_id and call_id not in {call["id"] for call in sequences[diagram_id]["calls"]}:
            fail(f"README deep link names unknown {document_id}/{diagram_id} call {call_id!r}")


def validate_source_refresh_contract() -> None:
    required_markers = {
        ROOT / "AGENTS.md": (
            "docs/source-refresh-runbook.md",
            "scripts/sync_source.py::DOCUMENTS",
            "scripts/build_data.py::DOCUMENT_CONFIGS",
            "Host Agent as the leftmost lane",
        ),
        ROOT / "README.md": (
            "docs/source-refresh-runbook.md",
            "Adding another Fundamentals sequence authority",
            "python3 scripts/sync_source.py ../fundamentals",
            "Selected Boot set cold start",
            "First boot installation",
            "dreamcatcher/bootset:current",
        ),
        RUNBOOK: (
            "Refresh an already registered authority",
            "Register a new sequence-document family",
            "managed external browser",
            "note-only `alt`/`else` branches",
            "`sequenceMeta` registry order",
            "Do **not** discover and publish every matching Fundamentals file automatically",
        ),
    }
    for path, markers in required_markers.items():
        text = path.read_text(encoding="utf-8")
        missing = [marker for marker in markers if marker not in text]
        if missing:
            fail(
                f"{path.relative_to(ROOT)} is missing source-refresh contract markers: "
                f"{', '.join(missing)}"
            )


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
    validate_source_refresh_contract()
    print("PASS: two exact source snapshots, generated data, app shell, navigation, and publication assets are valid")


if __name__ == "__main__":
    main()
