#!/usr/bin/env python3
"""Build the static Lifecycle Atlas bundle from exact authoritative Markdown snapshots."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"
MANIFEST_PATH = SOURCE_DIR / "manifest.json"
OUTPUT_PATH = ROOT / "site" / "data.js"

CHAMBERS_SEQUENCE_META: dict[str, dict[str, str]] = {
    "Mode 1 - Host activation": {
        "id": "host-activation",
        "shortTitle": "Engine cold start",
        "kicker": "Mode 1 · startup boundary",
        "summary": "How a running procman uses boot custody and the trusted host runtime to create the selected Engine Chamber.",
        "question": "What happens from authenticated host wake until the selected I3 Engine is ready?",
        "status": "current",
    },
    "Ordinary Chamber activation kernel": {
        "id": "activation-kernel",
        "shortTitle": "Ordinary activation",
        "kicker": "Shared primitive · Engine ready",
        "summary": "How an exact non-Engine Realization becomes a fresh, admitted, routable Chamber.",
        "question": "What must be true before a newly started ordinary Chamber is actually ready?",
        "status": "core",
    },
    "Mode 2 - Form and activate a candidate": {
        "id": "candidate-formation",
        "shortTitle": "Form a candidate",
        "kicker": "Mode 2",
        "summary": "How a locator or lock becomes an exact candidate without changing current.",
        "question": "How are resolution, build, acceptance, custody, and execution kept separate?",
        "status": "current",
    },
    "Mode 3 - Fenced development": {
        "id": "fenced-development",
        "shortTitle": "Fenced development",
        "kicker": "Mode 3",
        "summary": "How a mutable workspace is edited, sealed, and closed without exposing a host path.",
        "question": "How does development produce immutable input without promoting a running Chamber?",
        "status": "current",
    },
    "Mode 4 - Build an artifact": {
        "id": "artifact-build",
        "shortTitle": "Build an artifact",
        "kicker": "Mode 4 · later",
        "summary": "How exact inputs produce sealed OCI bytes and a receipt—but not acceptance.",
        "question": "Where does building end, and why is the output not current yet?",
        "status": "later",
    },
    "Later mode - Attested multi-Ark builds": {
        "id": "attested-builds",
        "shortTitle": "Attested builds",
        "kicker": "Later mode",
        "summary": "How independent builders, attestations, and inspectors strengthen artifact evidence.",
        "question": "What does multi-Ark convergence prove, and what still needs policy judgment?",
        "status": "later",
    },
    "Mode 5 - Verify a candidate": {
        "id": "candidate-verification",
        "shortTitle": "Verify a candidate",
        "kicker": "Mode 5",
        "summary": "How exact candidate and fixture Chambers are tested, evidenced, and reaped.",
        "question": "How can a verdict remain exact even after its test Chambers disappear?",
        "status": "current",
    },
    "Mode 6 - Select or roll back": {
        "id": "selection-rollback",
        "shortTitle": "Select or roll back",
        "kicker": "Mode 6",
        "summary": "How one fenced compare-and-swap changes current without moving any Chamber.",
        "question": "What changes at selection time—and what deliberately does not?",
        "status": "current",
    },
    "Mode 7 - Quiesce and wake": {
        "id": "quiesce-wake",
        "shortTitle": "Quiesce and wake",
        "kicker": "Mode 7",
        "summary": "How live Chambers stop while selections, custody, receipts, and resources survive.",
        "question": "What must be flushed and handed off before the final Engine disappears?",
        "status": "current",
    },
}

CARDFLOW_SEQUENCE_META: dict[str, dict[str, str]] = {
    "Mode 1 - Register and claim logical resources": {
        "id": "register-claim",
        "shortTitle": "Register and claim",
        "kicker": "Mode 1",
        "summary": "How canonical resources become one all-or-none logical lease set for a card.",
        "question": "How does Cardflow grant a bounded mutation claim without leaking physical authority?",
        "status": "working",
    },
    "Mode 2 - Queue, inspect, and wait": {
        "id": "queue-inspect-wait",
        "shortTitle": "Queue, inspect, and wait",
        "kicker": "Mode 2",
        "summary": "How blocked cards inspect a revisioned queue, yield durably, and wake without polling.",
        "question": "How can a waiter remain observable and resumable without holding a live worker?",
        "status": "working",
    },
    "Mode 3 - Materialize the first Chamber session": {
        "id": "materialize-session",
        "shortTitle": "Materialize first session",
        "kicker": "Mode 3",
        "summary": "How an active logical lease becomes an exact writable workspace and fresh Chamber session.",
        "question": "Where does Cardflow authority stop and physical owner authority begin?",
        "status": "working",
    },
    "Mode 4 - Continue through another Chamber lease": {
        "id": "continue-session",
        "shortTitle": "Continue in a fresh Chamber",
        "kicker": "Mode 4",
        "summary": "How one logical holder continues the same workspace lineage through a fresh Chamber.",
        "question": "Which identities remain stable, and which physical authorities must be minted again?",
        "status": "working",
    },
    "Mode 5 - Renew bounded leases": {
        "id": "renew-leases",
        "shortTitle": "Renew bounded leases",
        "kicker": "Mode 5",
        "summary": "How Cardflow, Chambers, and Filesystem renew one exact session without widening scope.",
        "question": "How is every physical deadline kept within the logical lease deadline?",
        "status": "working",
    },
    "Mode 6 - Release and hand off to the next card": {
        "id": "release-handoff",
        "shortTitle": "Release and hand off",
        "kicker": "Mode 6",
        "summary": "How physical cleanup reaches terminal receipts before logical ownership advances.",
        "question": "What barrier prevents the next card from inheriting unresolved physical effects?",
        "status": "working",
    },
    "Mode 7 - Cancel, expire, or terminalize": {
        "id": "cancel-expire",
        "shortTitle": "Cancel or expire",
        "kicker": "Mode 7",
        "summary": "How queued cancellation and active expiry diverge into safe terminal paths.",
        "question": "When can Cardflow finish locally, and when must it revoke and reconcile a session?",
        "status": "working",
    },
    "Mode 8 - Recover and reconcile": {
        "id": "recover-reconcile",
        "shortTitle": "Recover and reconcile",
        "kicker": "Mode 8",
        "summary": "How startup recovery compares durable intent with owner observations before acting.",
        "question": "How does reconciliation avoid blindly replaying materialization after a crash?",
        "status": "working",
    },
    "Mode 9 - Reject bypass and stale authority": {
        "id": "reject-bypass",
        "shortTitle": "Reject bypass and staleness",
        "kicker": "Mode 9",
        "summary": "How owner gates reject unauthorized acquisition, stale dispatch, and stale mutation.",
        "question": "Which layer rejects each attempt to bypass current logical or physical authority?",
        "status": "working",
    },
}

DOCUMENT_CONFIGS: OrderedDict[str, dict[str, Any]] = OrderedDict(
    [
        (
            "chambers",
            {
                "id": "chambers",
                "name": "Chambers",
                "title": "Chambers lifecycle",
                "subtitle": "Immutable Realizations, fresh Chambers, evidence, selection, and wake",
                "description": "Explore how exact Realizations become admitted Chambers and move through development, verification, selection, rollback, and quiescence.",
                "functionHeading": "Engine function table",
                "functionIntro": "Every I3 and conventional host-boundary function named by the Chambers lifecycle sequences.",
                "manifestSnapshot": "chambers-lifecycle-sequences.md",
                "sequenceMeta": CHAMBERS_SEQUENCE_META,
                "accent": "cyan",
                "statusLabel": "Current architecture",
            },
        ),
        (
            "cardflow",
            {
                "id": "cardflow",
                "name": "Cardflow",
                "title": "Cardflow filesystem leases",
                "subtitle": "Logical claims, physical sessions, cleanup barriers, and recovery",
                "description": "Explore the two-layer lease architecture joining Cardflow's logical ownership to Filesystem and Chambers physical authority.",
                "functionHeading": "I3 function table",
                "functionIntro": "Every namespaced I3 contract used to claim, wait, materialize, renew, release, reconcile, and reject stale authority.",
                "manifestSnapshot": "cardflow-filesystem-lease-sequences.md",
                "sequenceMeta": CARDFLOW_SEQUENCE_META,
                "accent": "violet",
                "statusLabel": "Working architecture",
            },
        ),
    ]
)


def clean_markdown(value: str) -> str:
    """Reduce Markdown/table prose to display-safe plain text."""
    value = html.unescape(value.strip())
    value = re.sub(r"<br\s*/?>", " · ", value, flags=re.IGNORECASE)
    value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", value)
    value = value.replace("`", "").replace("**", "").replace("__", "")
    value = re.sub(r"(?<!\w)[*_](.*?)[*_](?!\w)", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def slugify(value: str) -> str:
    value = value.lower().replace("–", "-").replace("—", "-")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def participant_role(label: str, participant_id: str) -> str:
    text = f"{label} {participant_id}".lower()
    if "procman" in text or "host runtime" in text or participant_id.lower() == "runtime":
        return "host"
    if any(word in text for word in ("filesystem", "custody", "cas", "provider", "vault")):
        return "resource"
    if any(
        word in text
        for word in ("verifier", "tester", "acceptor", "promoter", "attestation", "inspector", "recovery")
    ):
        return "assurance"
    if any(word in text for word in ("supervisor", "cardflow", "engine")):
        return "control" if "engine" not in text else "engine"
    if any(word in text for word in ("chamber", "builder", "candidate", "fixture", "developer", "members")):
        return "chamber"
    return "caller"


def implementation_status(raw_function_cell: str) -> str:
    lowered = raw_function_cell.lower()
    if "contract extension required" in lowered:
        return "contract-extension-required"
    if re.search(r"\brequired\b", lowered):
        return "required"
    if "optional later" in lowered or "later" in lowered:
        return "optional-later"
    return "existing"


def parse_function_table(
    lines: list[str], table_heading: str
) -> OrderedDict[str, dict[str, Any]]:
    registry: OrderedDict[str, dict[str, Any]] = OrderedDict()
    in_table_section = False
    owner = ""
    target = f"## {table_heading}"

    for line_number, line in enumerate(lines, start=1):
        if line.startswith(target):
            in_table_section = True
            continue
        if in_table_section and line.startswith("## "):
            break
        if not in_table_section:
            continue
        if line.startswith("### "):
            owner = clean_markdown(line[4:])
            continue
        if not line.lstrip().startswith("|"):
            continue

        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0] in {"Function", "---"} or set(cells[0]) <= {"-", ":"}:
            continue
        match = re.search(r"`([^`]+)`", cells[0])
        if not match:
            continue

        function_id = match.group(1).strip()
        invocation_path = clean_markdown(cells[1])
        contract = clean_markdown(" | ".join(cells[2:]))
        status = implementation_status(cells[0])
        kind = "host" if "not I3" in invocation_path else "i3"
        registry[function_id] = {
            "id": function_id,
            "owner": owner or "Document contract",
            "path": invocation_path,
            "kind": kind,
            "implementationStatus": status,
            "contract": contract,
            "sourceLine": line_number,
            "usages": [],
        }

    if not registry:
        raise ValueError(f"No rows were parsed from {table_heading!r}")
    return registry


def context_snapshot(stack: list[dict[str, str]]) -> list[dict[str, str]]:
    return [dict(item) for item in stack]


def parse_mermaid_sequence(
    block: list[tuple[int, str]],
    title: str,
    registry: OrderedDict[str, dict[str, Any]],
    ordinal: int,
    sequence_meta: dict[str, dict[str, str]],
) -> dict[str, Any]:
    meta = dict(sequence_meta.get(title, {}))
    diagram_id = meta.pop("id", slugify(title))
    meta.setdefault("shortTitle", title)
    meta.setdefault("kicker", f"Sequence {ordinal}")
    meta.setdefault("summary", "Explore the exact actors and calls in this lifecycle sequence.")
    meta.setdefault("question", "How do authority and effects move across this sequence?")
    meta.setdefault("status", "current")

    participants: list[dict[str, Any]] = []
    participant_index: dict[str, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    fragments: list[dict[str, Any]] = []
    fragment_counter = 0

    for source_line, raw_line in block:
        stripped = raw_line.strip()
        if not stripped or stripped in {"sequenceDiagram", "autonumber"}:
            continue

        participant_match = re.match(
            r"^(actor|participant)\s+([A-Za-z0-9_]+)(?:\s+as\s+(.+))?$", stripped
        )
        if participant_match:
            participant_type, participant_id, label = participant_match.groups()
            label = clean_markdown(label or participant_id)
            participant = {
                "id": participant_id,
                "label": label,
                "type": participant_type,
                "role": participant_role(label, participant_id),
                "order": len(participants),
            }
            participants.append(participant)
            participant_index[participant_id] = participant
            continue

        if stripped.startswith("alt "):
            fragment_counter += 1
            label = clean_markdown(stripped[4:])
            fragments.append(
                {"id": f"fragment-{fragment_counter}", "type": "alt", "label": label, "branch": label}
            )
            continue
        if stripped == "else" or stripped.startswith("else "):
            if fragments:
                branch = clean_markdown(stripped[5:]) if len(stripped) > 4 else "Otherwise"
                fragments[-1]["branch"] = branch
            continue
        if stripped.startswith("opt "):
            fragment_counter += 1
            label = clean_markdown(stripped[4:])
            fragments.append(
                {"id": f"fragment-{fragment_counter}", "type": "opt", "label": label, "branch": label}
            )
            continue
        if stripped.startswith("loop "):
            fragment_counter += 1
            label = clean_markdown(stripped[5:])
            fragments.append(
                {"id": f"fragment-{fragment_counter}", "type": "loop", "label": label, "branch": label}
            )
            continue
        if stripped.startswith("par "):
            fragment_counter += 1
            label = clean_markdown(stripped[4:])
            fragments.append(
                {"id": f"fragment-{fragment_counter}", "type": "par", "label": label, "branch": label}
            )
            continue
        if stripped.startswith("and "):
            if fragments:
                fragments[-1]["branch"] = clean_markdown(stripped[4:])
            continue
        if stripped == "end":
            if fragments:
                fragments.pop()
            continue

        note_match = re.match(
            r"^Note\s+(over|right of|left of)\s+([^:]+):\s*(.+)$", stripped, flags=re.IGNORECASE
        )
        if note_match:
            placement, actor_text, text = note_match.groups()
            actor_ids = [item.strip() for item in actor_text.split(",")]
            notes.append(
                {
                    "id": f"{diagram_id}-note-{len(notes) + 1}",
                    "placement": placement.lower(),
                    "actors": actor_ids,
                    "text": clean_markdown(text),
                    "sourceLine": source_line,
                    "context": context_snapshot(fragments),
                }
            )
            continue

        call_match = re.match(
            r"^([A-Za-z0-9_]+)\s*(?:-->>|->>|-->|->)\s*([A-Za-z0-9_]+)\s*:\s*(.+)$",
            stripped,
        )
        if call_match:
            sender, receiver, message = call_match.groups()
            function_match = re.search(r"`([^`]+)`", message)
            function_id = clean_markdown(function_match.group(1) if function_match else message)
            if function_id not in registry:
                raise ValueError(
                    f"Unknown function {function_id!r} in {title!r} at source line {source_line}"
                )
            if sender not in participant_index or receiver not in participant_index:
                raise ValueError(
                    f"Unknown participant in {sender}->{receiver} at source line {source_line}"
                )
            function = registry[function_id]
            call = {
                "id": f"{diagram_id}-call-{len(calls) + 1}",
                "index": len(calls),
                "from": sender,
                "to": receiver,
                "function": function_id,
                "kind": function["kind"],
                "context": context_snapshot(fragments),
                "notes": [],
                "sourceLine": source_line,
            }
            calls.append(call)
            continue

    if not participants or not calls:
        raise ValueError(f"Sequence {title!r} has no participants or calls")

    for note in notes:
        note_context = note["context"]
        same_or_descendant = [
            call for call in calls
            if call["context"][:len(note_context)] == note_context
        ]
        ancestor = [
            call for call in calls
            if note_context[:len(call["context"])] == call["context"]
        ]
        candidates = same_or_descendant or ancestor or calls
        nearest = min(
            candidates,
            key=lambda call: (abs(call["sourceLine"] - note["sourceLine"]), call["sourceLine"]),
        )
        nearest["notes"].append(note)

    for call in calls:
        function = registry[call["function"]]
        usage = {
            "diagramId": diagram_id,
            "diagramTitle": meta["shortTitle"],
            "callId": call["id"],
            "step": call["index"] + 1,
            "from": call["from"],
            "to": call["to"],
        }
        function["usages"].append(usage)

    kinds = Counter(call["kind"] for call in calls)
    return {
        "id": diagram_id,
        "title": title,
        "shortTitle": meta["shortTitle"],
        "kicker": meta["kicker"],
        "summary": meta["summary"],
        "question": meta["question"],
        "status": meta["status"],
        "ordinal": ordinal,
        "sourceLine": block[0][0] if block else 0,
        "participants": participants,
        "calls": calls,
        "stats": {
            "actors": len(participants),
            "calls": len(calls),
            "i3Calls": kinds.get("i3", 0),
            "hostCalls": kinds.get("host", 0),
            "notes": len(notes),
            "branches": len(
                {
                    (context["id"], context["branch"])
                    for call in calls
                    for context in call["context"]
                }
            ),
        },
    }


def parse_sequences(
    lines: list[str],
    registry: OrderedDict[str, dict[str, Any]],
    sequence_meta: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    sequences: list[dict[str, Any]] = []
    current_h2 = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        if line.startswith("## ") and not line.startswith("### "):
            current_h2 = clean_markdown(line[3:])
        if line.strip() == "```mermaid":
            block: list[tuple[int, str]] = []
            cursor = index + 1
            while cursor < len(lines) and lines[cursor].strip() != "```":
                block.append((cursor + 1, lines[cursor]))
                cursor += 1
            if block and block[0][1].strip() == "sequenceDiagram":
                sequences.append(
                    parse_mermaid_sequence(
                        block, current_h2, registry, len(sequences) + 1, sequence_meta
                    )
                )
            index = cursor
        index += 1

    if not sequences:
        raise ValueError("No Mermaid sequenceDiagram blocks were parsed")
    ids = [sequence["id"] for sequence in sequences]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate sequence ids: {ids}")
    expected_titles = set(sequence_meta)
    actual_titles = {sequence["title"] for sequence in sequences}
    if expected_titles != actual_titles:
        raise ValueError(
            f"Sequence metadata/source mismatch; missing={sorted(expected_titles - actual_titles)}, "
            f"unexpected={sorted(actual_titles - expected_titles)}"
        )

    display_order = {title: index for index, title in enumerate(sequence_meta)}
    sequences.sort(key=lambda sequence: display_order[sequence["title"]])
    sequence_rank: dict[str, int] = {}
    for ordinal, sequence in enumerate(sequences, start=1):
        sequence["ordinal"] = ordinal
        sequence_rank[sequence["id"]] = ordinal
    for function in registry.values():
        function["usages"].sort(
            key=lambda usage: (sequence_rank[usage["diagramId"]], usage["step"])
        )
    return sequences


def build_document(
    config: dict[str, Any], manifest: dict[str, Any], source_entry: dict[str, Any]
) -> dict[str, Any]:
    source_path = SOURCE_DIR / source_entry["snapshotPath"]
    if source_path.parent != SOURCE_DIR or not source_path.exists():
        raise FileNotFoundError(f"Missing or invalid source snapshot: {source_path}")
    source_bytes = source_path.read_bytes()
    actual_digest = hashlib.sha256(source_bytes).hexdigest()
    if source_entry.get("documentSha256") != actual_digest:
        raise ValueError(f"Manifest digest does not match {source_entry['snapshotPath']}")

    lines = source_bytes.decode("utf-8").splitlines()
    registry = parse_function_table(lines, config["functionHeading"])
    sequences = parse_sequences(lines, registry, config["sequenceMeta"])
    function_list = list(registry.values())
    all_calls = [call for sequence in sequences for call in sequence["calls"]]
    kinds = Counter(call["kind"] for call in all_calls)
    source = dict(source_entry)
    source["repository"] = manifest["repository"]
    source["repositoryHead"] = manifest["repositoryHead"]
    source["url"] = (
        f"https://github.com/{manifest['repository']}/blob/"
        f"{source_entry['sourceCommit']}/{source_entry['path']}"
    )

    return {
        "id": config["id"],
        "name": config["name"],
        "title": config["title"],
        "subtitle": config["subtitle"],
        "description": config["description"],
        "functionIntro": config["functionIntro"],
        "accent": config["accent"],
        "statusLabel": config["statusLabel"],
        "source": source,
        "stats": {
            "sequences": len(sequences),
            "actors": len(
                {
                    participant["label"]
                    for sequence in sequences
                    for participant in sequence["participants"]
                }
            ),
            "calls": len(all_calls),
            "i3Calls": kinds.get("i3", 0),
            "hostCalls": kinds.get("host", 0),
            "functions": len(function_list),
            "usedFunctions": sum(bool(function["usages"]) for function in function_list),
        },
        "sequences": sequences,
        "functions": function_list,
    }


def build_payload() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Missing source manifest: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("schemaVersion") != 2:
        raise ValueError("source/manifest.json must use schemaVersion 2")

    entries = {entry["id"]: entry for entry in manifest.get("documents", [])}
    if set(entries) != set(DOCUMENT_CONFIGS):
        raise ValueError(
            f"Manifest documents must be exactly {sorted(DOCUMENT_CONFIGS)}; got {sorted(entries)}"
        )
    documents = [
        build_document(config, manifest, entries[document_id])
        for document_id, config in DOCUMENT_CONFIGS.items()
    ]
    combined = {
        "documents": len(documents),
        "sequences": sum(document["stats"]["sequences"] for document in documents),
        "calls": sum(document["stats"]["calls"] for document in documents),
        "functions": sum(document["stats"]["functions"] for document in documents),
    }
    return {
        "schemaVersion": 2,
        "product": {
            "name": "Lifecycle Atlas",
            "subtitle": "Chambers and Cardflow sequence explorer",
        },
        "defaultDocumentId": "chambers",
        "stats": combined,
        "documents": documents,
    }


def render_bundle(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    return (
        "/* Generated by scripts/build_data.py. Do not edit by hand. */\n"
        f"window.LIFECYCLE_ATLAS_DATA = {serialized};\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if site/data.js is stale")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        payload = build_payload()
        rendered = render_bundle(payload)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != rendered:
            print("ERROR: site/data.js is stale; run python3 scripts/build_data.py", file=sys.stderr)
            return 1
        print("PASS: site/data.js exactly matches both source documents")
    else:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(rendered, encoding="utf-8")
        print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")

    if args.print_summary:
        for document in payload["documents"]:
            stats = document["stats"]
            print(
                f"{document['name']}: {stats['sequences']} sequences · {stats['calls']} calls · "
                f"{stats['i3Calls']} I3 · {stats['hostCalls']} host-boundary · "
                f"{stats['functions']} functions"
            )
        stats = payload["stats"]
        print(
            f"Combined: {stats['documents']} documents · {stats['sequences']} sequences · "
            f"{stats['calls']} calls · {stats['functions']} functions"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
