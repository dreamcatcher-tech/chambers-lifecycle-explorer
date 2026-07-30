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
    if manifest.get("schemaVersion") != 3:
        fail("source manifest schemaVersion must be 3")
    if payload.get("schemaVersion") != 2:
        fail("browser bundle schemaVersion must be 2")
    if payload.get("defaultDocumentId") != "chambers":
        fail("default document must remain Chambers")
    formal_authority = manifest.get("formalAuthority", {})
    if payload.get("formalAuthority") != formal_authority:
        fail("browser bundle formal authority does not match source manifest")
    if formal_authority.get("repository") != "dreamcatcher-tech/chambers-temporal-model":
        fail("Chambers formal authority repository is wrong")
    if formal_authority.get("git_tag") != "formal-spec-v1.0.0":
        fail("Chambers formal authority tag drifted")
    if formal_authority.get("commit") != "72f7dc531392b71cd210163649b4944a38b5edaa":
        fail("Chambers formal authority commit drifted")

    documents = payload.get("documents", [])
    if [document.get("id") for document in documents] != ["chambers", "cardflow"]:
        fail("bundle must contain Chambers and Cardflow in that order")
    expected_stats = {"documents": 2, "sequences": 26, "calls": 212, "functions": 90, "dictionaryTerms": 87}
    if payload.get("stats") != expected_stats:
        fail(f"unexpected combined stats: {payload.get('stats')}")

    entries = {entry["id"]: entry for entry in manifest["documents"]}
    expected_roles = {
        "chambers": "downstream_projection_of_chambers_formal_specification_v1.0.0",
        "cardflow": "cardflow_design_source_with_chambers_formal_release_binding",
    }
    for document in documents:
        entry = entries.get(document["id"])
        source = document["source"]
        if not entry:
            fail(f"manifest is missing {document['id']}")
        assert entry is not None
        if entry.get("role") != expected_roles[document["id"]] or source.get("role") != expected_roles[document["id"]]:
            fail(f"{document['id']} registered-source role is wrong")
        snapshot = SOURCE / entry["snapshotPath"]
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        if digest != entry.get("documentSha256") or digest != source.get("documentSha256"):
            fail(f"{document['id']} source hash binding failed")
        expected_url = f"https://github.com/{manifest['repository']}/blob/{entry['sourceCommit']}/{entry['path']}"
        if source.get("url") != expected_url:
            fail(f"{document['id']} exact source URL is wrong")
        if not document.get("sequences") or not document.get("functions") or not document.get("dictionary"):
            fail(f"{document['id']} has no generated sequence/function/dictionary content")
        function_ids = {fn["id"] for fn in document["functions"]}
        if any(call["function"] not in function_ids for sequence in document["sequences"] for call in sequence["calls"]):
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
    expected_chambers = {
        "sequences": 17, "actors": 47, "calls": 146, "i3Calls": 135,
        "hostCalls": 11, "functions": 57, "usedFunctions": 57, "dictionaryTerms": 57,
    }
    if chambers["stats"] != expected_chambers:
        fail(f"unexpected Chambers stats: {chambers['stats']}")
    expected_cardflow = {
        "sequences": 9, "actors": 19, "calls": 66, "i3Calls": 66,
        "hostCalls": 0, "functions": 33, "usedFunctions": 31, "dictionaryTerms": 30,
    }
    if cardflow["stats"] != expected_cardflow:
        fail(f"unexpected Cardflow stats: {cardflow['stats']}")

    expected_startup = [
        "core-installation", "host-activation", "core-bootstrap", "boot-crash-repair",
        "scope-bound-child-core", "ark-peer-interconnect", "activation-kernel",
    ]
    if [sequence["id"] for sequence in chambers["sequences"][:7]] != expected_startup:
        fail("Chambers must present install, cold start, bootstrap, whole recovery, child Core, Ark peer interconnect, then ordinary activation")

    host_i3 = {
        "ark::core::activate", "ark::core::inspect", "ark::core::quiesce",
        "ark::core::restart", "ark::core::stage", "ark::child::stop",
        "chamber::activate", "chamber::inspect", "chamber::stop",
    }
    worker_order = ["Engine", "Persistence", "Gateway", "Supervisor"]
    forbidden_lanes = {"containerd", "BootControl", "Volume", "Materializer", "Runtime", "Router", "NextRouter"}
    forbidden_function_prefixes = ("containerd_", "persistence_volume_", "bootset_")
    for sequence in chambers["sequences"]:
        participants = [participant["id"] for participant in sequence["participants"]]
        participant_roles = {participant["id"]: participant["role"] for participant in sequence["participants"]}
        if "HostAgent" in participants and participants[0] != "HostAgent":
            fail(f"{sequence['id']} does not keep Host Agent leftmost")
        present_forbidden = forbidden_lanes.intersection(participants)
        if present_forbidden:
            fail(f"{sequence['id']} retains low-level or removed lanes: {sorted(present_forbidden)}")
        present = [item for item in worker_order if item in participants]
        positions = [participants.index(item) for item in present]
        if positions != sorted(positions):
            fail(f"{sequence['id']} violates Engine/Persistence/Gateway/Supervisor worker order")
        for call in sequence["calls"]:
            if call["function"].startswith(forbidden_function_prefixes):
                fail(f"{sequence['id']} exposes low-level host call {call['function']}")
            if call["function"] in host_i3 and call["to"] != "HostAgent":
                fail(f"{sequence['id']} aims a Host Agent I3 function at {call['to']}")
            if call["function"].startswith("ark::peer::") and participant_roles.get(call["to"]) != "control":
                fail(f"{sequence['id']} aims an Ark Interconnect function at non-Gateway actor {call['to']}")

    sequence_by_id = {sequence["id"]: sequence for sequence in chambers["sequences"]}
    host_activation = sequence_by_id["host-activation"]
    host_calls = [call["function"] for call in host_activation["calls"]]
    if host_calls.count("wake_ark_core") != 1 or "start_ark_core" not in host_calls:
        fail("selected Ark Core cold start must use one wake and the one intent-level Core-start macro")
    if any(call.startswith(forbidden_function_prefixes) for call in host_calls):
        fail("selected Ark Core cold start leaks lower runtime subcommands")
    host_participants = [participant["id"] for participant in host_activation["participants"]]
    if [item for item in ("Core", "Persistence", "Gateway", "Supervisor") if item in host_participants] != [
        "Core", "Persistence", "Gateway", "Supervisor",
    ]:
        fail("selected Ark Core cold start must declare Core, Persistence, Gateway, Supervisor in order")

    all_calls = [call for sequence in chambers["sequences"] for call in sequence["calls"]]
    for call in all_calls:
        if call["to"] == "Engine":
            fail("Engine must not own a Dreamcatcher lifecycle function")
        if call["from"] == "Engine" and not (
            call["to"] == "Gateway"
            and call["function"] in {"routing::authenticate", "routing::authorize_registration"}
        ):
            fail("Engine may invoke only fixed Gateway authentication and registration hooks")
        if call["function"].startswith("routing::") and call["to"] != "Gateway":
            fail("every routing function must target Gateway")

        if call["function"].startswith("persistence::") and call["to"] != "Persistence":
            fail("every persistence function must target Persistence")
        if call["from"] == "HostAgent" and call["function"] in {
            "routing::reconcile", "routing::fence", "routing::install", "routing::reopen",
        }:
            fail("Host Agent must not mutate Gateway state")

    roles_by_id: dict[str, set[str]] = {}
    for sequence in chambers["sequences"]:
        for participant in sequence["participants"]:
            roles_by_id.setdefault(participant["id"], set()).add(participant["role"])
    if roles_by_id.get("Persistence") != {"resource"}:
        fail(f"Persistence must remain a resource actor, got {roles_by_id.get('Persistence')}")
    if roles_by_id.get("Gateway") != {"control"}:
        fail(f"Gateway must remain a control actor, got {roles_by_id.get('Gateway')}")
    if roles_by_id.get("Engine") != {"engine"}:
        fail(f"Engine must remain an engine actor, got {roles_by_id.get('Engine')}")

    chambers_snapshot = (SOURCE / chambers["source"]["snapshotPath"]).read_text(encoding="utf-8")
    flattened = chambers_snapshot.replace("\n", " ")
    required_core_markers = (
        "one exact OCI image, one gVisor task, one s6 PID 1",
        "boot-control/selected.json",
        "any required Core process exit or semantic-readiness loss -> complete Core-task exit -> complete scope recovery",
        "s6 as container PID 1, with one-shot bootstrap seeding accepted runtime bytes into private `/run/iii` tmpfs",
        "127.0.0.1:49133",
        "Ark-private scope listener at port `49134`",
        "explicit inter-scope forwarding-deny fence",
        "ordinary descendants receive no Ark-volume contents",
        "22/22 independently verified checks",
        "s6 whole-appliance fatality, production containerd/CNI-plugin, and storage-driver integration require their own acceptance evidence",
        "no member-local restart path",
        "Gateway warm cutover applies only to ordinary Chambers",
        "one-attempt LKG fallback",
        "Builder as an ordinary separate sandbox",
    )
    missing_core_markers = [marker for marker in required_core_markers if marker not in flattened]
    if missing_core_markers:
        fail(f"Chambers Ark Core authority contract is incomplete: {missing_core_markers}")
    for retired in ("Boot set", "Boot-set", "bootset::", "repair_boot_member"):
        if retired in chambers_snapshot:
            fail(f"retired four-member Core vocabulary remains: {retired}")

    bootstrap_calls = [call["function"] for call in sequence_by_id["core-bootstrap"]["calls"]]
    if bootstrap_calls.count("routing::authenticate") != 2 or bootstrap_calls.count("routing::authorize_registration") != 2:
        fail("Ark Core bootstrap must install Gateway hooks and admit scope-bound ProcMan")
    bootstrap_notes = " ".join(
        note["text"] for call in sequence_by_id["core-bootstrap"]["calls"] for note in call["notes"]
    )
    for required in ("private /run/iii tmpfs", "127.0.0.1:49133", "scope-IP:49134"):
        if required not in bootstrap_notes:
            fail(f"Ark Core bootstrap projection is missing {required}")

    selection_calls = [call["function"] for call in sequence_by_id["selection-rollback"]["calls"]]
    for required in ("ark::core::stage", "persistence::core::commit", "ark::core::restart"):
        if required not in selection_calls:
            fail(f"Ark Core selection is missing {required}")
    if not (
        selection_calls.index("ark::core::stage")
        < selection_calls.index("persistence::core::commit")
        < selection_calls.index("ark::core::restart")
    ):
        fail("Core staging, atomic Persistence commit, and complete restart are out of order")

    ordinary_cutover = [call["function"] for call in sequence_by_id["ordinary-routed-cutover"]["calls"]]
    for required in (
        "persistence::routing::prepare", "routing::fence", "persistence::selection::commit",
        "routing::install", "routing::reopen", "persistence::routing::complete",
    ):
        if required not in ordinary_cutover:
            fail(f"ordinary routed cutover is missing {required}")
    if "persistence::core::commit" in ordinary_cutover or "ark::core::restart" in ordinary_cutover:
        fail("ordinary routed cutover must not mutate or restart the Ark Core")

    replacement_calls = [call["function"] for call in sequence_by_id["core-cutover"]["calls"]]
    for required in (
        "ark::core::stage", "ark::core::inspect", "persistence::core::commit",
        "ark::core::restart", "start_ark_core",
    ):
        if required not in replacement_calls:
            fail(f"complete Ark Core replacement is missing {required}")
    if "routing::install" in replacement_calls or "routing::reopen" in replacement_calls:
        fail("Core replacement must not use ordinary routed handover")

    recovery_calls = [call["function"] for call in sequence_by_id["boot-crash-repair"]["calls"]]
    if "recover_ark_tree" not in recovery_calls or "start_ark_core" not in recovery_calls:
        fail("whole-appliance recovery must reap the scope tree and start one fresh Core")
    if "persistence::core::commit" in recovery_calls or "ark::core::restart" in recovery_calls:
        fail("same-selection whole-appliance recovery must not mutate Core selection")

    child_calls = [call["function"] for call in sequence_by_id["scope-bound-child-core"]["calls"]]
    for required in ("ark::core::activate", "start_ark_core", "chamber::activate", "ark::child::stop"):
        if required not in child_calls:
            fail(f"scope-bound child Core sequence is missing {required}")
    child_notes = " ".join(
        note["text"] for call in sequence_by_id["scope-bound-child-core"]["calls"] for note in call["notes"]
    )
    for required in (
        "payload parent/routing fields are rejected",
        "deny forwarding to parent and sibling scope networks",
        "Parenthood grants no inspection, data, route, policy, or ordinary-control capability",
    ):
        if required not in child_notes:
            fail(f"scope-bound child Core projection is missing {required}")

    peer_calls = [call["function"] for call in sequence_by_id["ark-peer-interconnect"]["calls"]]
    if set(peer_calls) != {
        "ark::peer::contact", "ark::peer::connect", "ark::peer::session::open", "ark::peer::disconnect",
    }:
        fail(f"Ark peer interconnect has an unexpected function surface: {peer_calls}")
    peer_notes = " ".join(
        note["text"] for call in sequence_by_id["ark-peer-interconnect"]["calls"] for note in call["notes"]
    )
    for required in (
        "receiver-issued invitation",
        "same-host, parent/child, sibling, and remote peers use the same end-to-end protocol",
        "ProcMan lifecycle channel are never exposed",
    ):
        if required not in peer_notes:
            fail(f"Ark peer interconnect projection is missing {required}")

    retired_functions = [
        function["id"] for function in chambers["functions"]
        if function["id"].startswith(forbidden_function_prefixes) or function["id"].startswith("bootset::")
    ]
    if retired_functions:
        fail(f"retired low-level or Boot-set function rows remain: {retired_functions}")


def validate_html_and_assets(payload: dict) -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    css = (SITE / "styles.css").read_text(encoding="utf-8")
    app = (SITE / "app.js").read_text(encoding="utf-8")

    required_ids = {
        "documentSwitcher", "mobileDocumentSelect", "mobileSceneSelect", "journeyList",
        "sourceDocumentLink", "formalAuthorityLink", "footerSource", "footerAuthority", "stickyActorHeader", "stickyActorSvg", "sequenceViewport", "sequenceSvg",
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

    for element_id in ("sourceDocumentLink", "formalAuthorityLink", "footerSource", "footerAuthority"):
        pattern = rf'<a[^>]*id="{element_id}"[^>]*target="_blank"[^>]*rel="noopener noreferrer"'
        if not re.search(pattern, html):
            fail(f"{element_id} must open the exact private source in a safe new page")
    for marker in ("formalAuthority.release_url", "formalAuthority.git_tag", "Downstream formal-release projection"):
        if marker not in app:
            fail(f"app.js is missing visible formal-authority marker: {marker}")

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
            "Adding another Fundamentals sequence source",
            "python3 scripts/sync_source.py ../fundamentals",
            "Selected Ark Core cold start",
            "First Ark Core installation",
            "boot-control/selected.json",
            "Whole-appliance crash recovery",
        ),
        RUNBOOK: (
            "Refresh an already registered projection",
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
        fail("generated data does not match the registered source snapshots")


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
