#!/usr/bin/env python3
"""Build the static Chambers Atlas data bundle from the authoritative Markdown copy."""

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
SOURCE_PATH = ROOT / "source" / "chambers-lifecycle-sequences.md"
METADATA_PATH = ROOT / "source" / "metadata.json"
OUTPUT_PATH = ROOT / "site" / "data.js"

SEQUENCE_META: dict[str, dict[str, str]] = {
    "Chamber activation kernel": {
        "id": "activation-kernel",
        "shortTitle": "Activation kernel",
        "kicker": "Shared primitive",
        "summary": "How one exact Realization becomes a fresh, admitted, routable Chamber.",
        "question": "What must be true before a newly started Chamber is actually ready?",
        "status": "core",
    },
    "Mode 1 - Host activation": {
        "id": "host-activation",
        "shortTitle": "Host activation",
        "kicker": "Mode 1",
        "summary": "How a cold host wakes the selected Engine and only the Chambers demanded by work.",
        "question": "How does work enter when the I3 Engine itself may be absent?",
        "status": "current",
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
    if "procman" in text:
        return "host"
    if any(word in text for word in ("filesystem", "custody", "cas", "provider", "vault")):
        return "resource"
    if any(
        word in text
        for word in ("verifier", "tester", "acceptor", "promoter", "attestation", "inspector")
    ):
        return "assurance"
    if "supervisor" in text:
        return "control"
    if "engine" in text:
        return "engine"
    if any(word in text for word in ("chamber", "builder", "candidate", "fixture", "developer", "members")):
        return "chamber"
    return "caller"


def parse_function_table(lines: list[str]) -> OrderedDict[str, dict[str, Any]]:
    registry: OrderedDict[str, dict[str, Any]] = OrderedDict()
    in_table_section = False
    owner = ""

    for line_number, line in enumerate(lines, start=1):
        if line.startswith("## Engine function table"):
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
        kind = "host" if "not I3" in invocation_path else "i3"
        later = "optional later" in cells[0].lower() or "later" in cells[0].lower()
        registry[function_id] = {
            "id": function_id,
            "owner": owner,
            "path": invocation_path,
            "kind": kind,
            "later": later,
            "contract": contract,
            "sourceLine": line_number,
            "usages": [],
        }

    if not registry:
        raise ValueError("No Engine function-table rows were parsed")
    return registry


def context_snapshot(stack: list[dict[str, str]]) -> list[dict[str, str]]:
    return [dict(item) for item in stack]


def parse_mermaid_sequence(
    block: list[tuple[int, str]],
    title: str,
    registry: OrderedDict[str, dict[str, Any]],
    ordinal: int,
) -> dict[str, Any]:
    meta = dict(SEQUENCE_META.get(title, {}))
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
                "outgoing": [],
                "incoming": [],
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
                "owner": function["owner"],
                "later": function["later"],
                "contract": function["contract"],
                "context": context_snapshot(fragments),
                "notes": [],
                "sourceLine": source_line,
            }
            calls.append(call)
            continue

    if not participants or not calls:
        raise ValueError(f"Sequence {title!r} has no participants or calls")

    # Attach each concise diagram note to its nearest call so playback has context without prose walls.
    for note in notes:
        nearest = min(calls, key=lambda call: (abs(call["sourceLine"] - note["sourceLine"]), call["sourceLine"]))
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
        participant_index[call["from"]]["outgoing"].append(call["function"])
        participant_index[call["to"]]["incoming"].append(call["function"])

    for participant in participants:
        outgoing_counts = Counter(participant["outgoing"])
        incoming_counts = Counter(participant["incoming"])
        participant["outgoing"] = [
            {"function": name, "count": count} for name, count in outgoing_counts.items()
        ]
        participant["incoming"] = [
            {"function": name, "count": count} for name, count in incoming_counts.items()
        ]

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
    lines: list[str], registry: OrderedDict[str, dict[str, Any]]
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
                    parse_mermaid_sequence(block, current_h2, registry, len(sequences) + 1)
                )
            index = cursor
        index += 1

    if not sequences:
        raise ValueError("No Mermaid sequenceDiagram blocks were parsed")
    ids = [sequence["id"] for sequence in sequences]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate sequence ids: {ids}")
    return sequences


def build_payload() -> dict[str, Any]:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Missing source document: {SOURCE_PATH}")
    if not METADATA_PATH.exists():
        raise FileNotFoundError(f"Missing source metadata: {METADATA_PATH}")

    source_bytes = SOURCE_PATH.read_bytes()
    source_text = source_bytes.decode("utf-8")
    lines = source_text.splitlines()
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    actual_digest = hashlib.sha256(source_bytes).hexdigest()
    if metadata.get("documentSha256") != actual_digest:
        raise ValueError(
            "source/metadata.json documentSha256 does not match the authoritative Markdown copy"
        )

    registry = parse_function_table(lines)
    sequences = parse_sequences(lines, registry)
    function_list = list(registry.values())
    all_calls = [call for sequence in sequences for call in sequence["calls"]]
    kinds = Counter(call["kind"] for call in all_calls)

    return {
        "schemaVersion": 1,
        "product": {
            "name": "Chambers Atlas",
            "subtitle": "Interactive lifecycle sequence explorer",
        },
        "source": metadata,
        "stats": {
            "sequences": len(sequences),
            "actors": len({participant["label"] for sequence in sequences for participant in sequence["participants"]}),
            "calls": len(all_calls),
            "i3Calls": kinds.get("i3", 0),
            "hostCalls": kinds.get("host", 0),
            "functions": len(function_list),
            "usedFunctions": sum(bool(function["usages"]) for function in function_list),
        },
        "sequences": sequences,
        "functions": function_list,
    }


def render_bundle(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, indent=2, ensure_ascii=False)
    return (
        "/* Generated by scripts/build_data.py. Do not edit by hand. */\n"
        f"window.CHAMBERS_DATA = {serialized};\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Fail if site/data.js is stale")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        payload = build_payload()
        rendered = render_bundle(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if not OUTPUT_PATH.exists() or OUTPUT_PATH.read_text(encoding="utf-8") != rendered:
            print("ERROR: site/data.js is stale; run python3 scripts/build_data.py", file=sys.stderr)
            return 1
        print("PASS: site/data.js exactly matches the source document")
    else:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(rendered, encoding="utf-8")
        print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)}")

    if args.print_summary:
        stats = payload["stats"]
        print(
            f"{stats['sequences']} sequences · {stats['calls']} calls · "
            f"{stats['i3Calls']} I3 · {stats['hostCalls']} host-boundary · "
            f"{stats['functions']} functions"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
