#!/usr/bin/env python3
"""Regenerate the public, bounded TLA+ visualization projection.

This script intentionally publishes no raw TLA+ module, TLC state label, or DOT
file. It runs the exact checked models, parses TLC's complete DOT state graph,
and emits only source identities, named operators/properties, aggregate states,
aggregate transitions, and check receipts. Human explanations and layout come
from tla_model_annotations.json and are validated against live module names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
ANNOTATIONS_PATH = SCRIPT_DIR / "tla_model_annotations.json"
DEFAULT_OUTPUT = ROOT / "source" / "tla-model-projection.json"
EXPECTED_REPOSITORY = "dreamcatcher-tech/chambers-temporal-model"
MODEL_ORDER = ("ark_core_appliance", "multi_ark", "host_cutover")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    cwd: Path,
    capture: bool = True,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        check=False,
    )
    if check and result.returncode != 0:
        output = (result.stdout or "").strip()
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n{output}"
        )
    return result


def git_value(repo: Path, *args: str) -> str:
    return run(["git", *args], cwd=repo).stdout.strip()


def verify_temporal_checkout(repo: Path, allow_dirty: bool) -> tuple[str, str]:
    if not (repo / ".git").exists():
        raise RuntimeError(f"not a Git checkout: {repo}")
    remote = git_value(repo, "remote", "get-url", "origin")
    if "chambers-temporal-model" not in remote:
        raise RuntimeError(f"unexpected temporal-model origin: {remote}")
    status = git_value(repo, "status", "--porcelain")
    if status and not allow_dirty:
        raise RuntimeError("temporal-model checkout is dirty; refusing a mixed projection")
    head = git_value(repo, "rev-parse", "HEAD")
    try:
        upstream = git_value(repo, "rev-parse", "@{upstream}")
    except RuntimeError as error:
        raise RuntimeError("temporal-model branch has no upstream") from error
    if head != upstream:
        raise RuntimeError(
            f"temporal-model HEAD {head} does not match upstream {upstream}; sync first"
        )
    committed_at = git_value(repo, "show", "-s", "--format=%cI", head)
    return head, committed_at


def parse_module(module_path: Path) -> dict[str, Any]:
    text = module_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    definitions: dict[str, int] = {}
    definition_pattern = re.compile(
        r"^([A-Za-z][A-Za-z0-9_]*)(?:\([^)]*\))?\s*=="
    )
    for line_number, line in enumerate(lines, 1):
        match = definition_pattern.match(line)
        if match:
            definitions[match.group(1)] = line_number

    variables: list[dict[str, Any]] = []
    in_variables = False
    for line_number, line in enumerate(lines, 1):
        if line.strip() == "VARIABLES":
            in_variables = True
            continue
        if in_variables and line.startswith("vars =="):
            break
        if in_variables:
            candidate = line.split("\\*", 1)[0].strip().rstrip(",")
            if candidate and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", candidate):
                variables.append({"name": candidate, "sourceLine": line_number})

    try:
        next_start = next(i for i, line in enumerate(lines) if line.startswith("Next =="))
        spec_start = next(
            i for i in range(next_start + 1, len(lines)) if lines[i].startswith("Spec ==")
        )
    except StopIteration as error:
        raise RuntimeError(f"could not locate Next/Spec in {module_path}") from error
    next_block = "\n".join(lines[next_start:spec_start])
    init_line = definitions.get("Init", 0)
    next_line = definitions.get("Next", len(lines) + 1)
    next_actions = [
        name
        for name, line_number in sorted(definitions.items(), key=lambda item: item[1])
        if init_line < line_number < next_line
        and name != "Next"
        and re.search(rf"\b{re.escape(name)}\b", next_block)
    ]

    return {
        "text": text,
        "lines": lines,
        "definitions": definitions,
        "variables": variables,
        "nextActions": next_actions,
    }


def parse_config(config_path: Path) -> dict[str, Any]:
    lines = config_path.read_text(encoding="utf-8").splitlines()
    specification = None
    invariants: list[str] = []
    properties: list[str] = []
    constants: dict[str, str] = {}
    in_constants = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("\\*"):
            continue
        if stripped.startswith("SPECIFICATION "):
            specification = stripped.split(None, 1)[1]
            in_constants = False
        elif stripped == "CONSTANTS":
            in_constants = True
        elif stripped.startswith("INVARIANT "):
            invariants.append(stripped.split(None, 1)[1])
            in_constants = False
        elif stripped.startswith("PROPERTY "):
            properties.append(stripped.split(None, 1)[1])
            in_constants = False
        elif in_constants and "=" in stripped:
            name, value = stripped.split("=", 1)
            constants[name.strip()] = value.strip()
    if not specification or len(invariants) != 1 or len(properties) != 1:
        raise RuntimeError(f"unexpected principal config shape: {config_path}")
    return {
        "specification": specification,
        "invariant": invariants[0],
        "property": properties[0],
        "constants": constants,
    }


NODE_PATTERN = re.compile(
    r'^(-?\d+) \[label="(.*)"(?:,style = filled)?\];?$'
)
EDGE_PATTERN = re.compile(
    r'^(-?\d+) -> (-?\d+) \[label="([^"]+)"'
)


def decode_dot_label(value: str) -> str:
    return value.replace('\\"', '"').replace("\\n", "\n")


def quoted_value(label: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(name)} = \"([^\"]+)\"", label)
    if not match:
        raise RuntimeError(f"DOT state is missing quoted variable {name}")
    return match.group(1)


def tuple_value(label: str, variable: str, dimensions: list[str]) -> dict[str, str]:
    assignment = re.search(rf"\b{re.escape(variable)} = \(([^\n]+)\)", label)
    if not assignment:
        raise RuntimeError(f"DOT state is missing tuple variable {variable}")
    value = assignment.group(1)
    result: dict[str, str] = {}
    for dimension in dimensions:
        match = re.search(rf"\b{re.escape(dimension)} :> \"([^\"]+)\"", value)
        if not match:
            raise RuntimeError(f"DOT state is missing {variable}[{dimension}]")
        result[dimension] = match.group(1)
    return result


def parse_dot(dot_path: Path, aggregation: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, str] = {}
    raw_edges: list[tuple[str, str, str]] = []
    for line in dot_path.read_text(encoding="utf-8").splitlines():
        node_match = NODE_PATTERN.match(line)
        if node_match:
            nodes[node_match.group(1)] = decode_dot_label(node_match.group(2))
            continue
        edge_match = EDGE_PATTERN.match(line)
        if edge_match:
            raw_edges.append(edge_match.groups())

    if not nodes:
        raise RuntimeError(f"no TLC states parsed from {dot_path}")
    for source, target, _ in raw_edges:
        if source not in nodes or target not in nodes:
            raise RuntimeError("DOT transition references an unknown state")

    kind = aggregation["kind"]
    variable = aggregation["variable"]

    def abstract_state(label: str) -> tuple[str, dict[str, str] | None]:
        if kind == "scalar":
            value = quoted_value(label, variable)
            return value, None
        if kind == "last_action":
            value = quoted_value(label, variable)
            return value, None
        if kind == "tuple":
            values = tuple_value(label, variable, aggregation["dimensions"])
            key = "|".join(values[name] for name in aggregation["dimensions"])
            return key, values
        raise RuntimeError(f"unsupported aggregation kind: {kind}")

    node_keys: dict[str, str] = {}
    node_values: dict[str, dict[str, str] | None] = {}
    node_counts: Counter[str] = Counter()
    for node_id, label in nodes.items():
        key, values = abstract_state(label)
        node_keys[node_id] = key
        node_values[key] = values
        node_counts[key] += 1

    transition_counts: Counter[tuple[str, str, str, str]] = Counter()
    for source, target, operator in raw_edges:
        concrete_action = quoted_value(nodes[target], "lastAction")
        transition_counts[
            (node_keys[source], node_keys[target], concrete_action, operator)
        ] += 1

    if kind == "tuple":
        value_order = {value: index for index, value in enumerate(aggregation["values"])}

        def node_sort(key: str) -> tuple[int, ...]:
            values = node_values[key] or {}
            return tuple(value_order[values[name]] for name in aggregation["dimensions"])

        ordered_keys = sorted(node_counts, key=node_sort)
    else:
        ordered_keys = list(node_counts)

    abstract_nodes: list[dict[str, Any]] = []
    for key in ordered_keys:
        item: dict[str, Any] = {"id": key, "concreteStates": node_counts[key]}
        values = node_values[key]
        if values is not None:
            item["values"] = values
            item["label"] = " · ".join(
                f"{name} {values[name]}" for name in aggregation["dimensions"]
            )
        abstract_nodes.append(item)

    abstract_transitions = [
        {
            "from": source,
            "to": target,
            "action": action,
            "operator": operator,
            "concreteTransitions": count,
        }
        for (source, target, action, operator), count in sorted(transition_counts.items())
    ]

    return {
        "concreteStateCount": len(nodes),
        "concreteTransitionCount": len(raw_edges),
        "nodes": abstract_nodes,
        "transitions": abstract_transitions,
    }


def run_tlc_dump(
    *,
    java: Path,
    tla_jar: Path,
    temporal_repo: Path,
    module: str,
    output_dir: Path,
) -> tuple[Path, str]:
    dot_path = output_dir / f"{module}.dot"
    command = [
        str(java),
        "-XX:+UseParallelGC",
        "-Xmx1g",
        "-cp",
        str(tla_jar),
        "tlc2.TLC",
        "-cleanup",
        "-deadlock",
        "-nowarning",
        "-workers",
        "1",
        "-dump",
        "dot,actionlabels,colorize",
        str(dot_path),
        "-config",
        f"model/{module}.cfg",
        f"model/{module}.tla",
    ]
    result = run(command, cwd=temporal_repo)
    if "Model checking completed. No error has been found." not in result.stdout:
        raise RuntimeError(f"TLC did not report success for {module}\n{result.stdout}")
    if not dot_path.is_file():
        raise RuntimeError(f"TLC did not create {dot_path}")
    return dot_path, result.stdout


def source_url(commit: str, path: str, line: int | None = None) -> str:
    base = f"https://github.com/{EXPECTED_REPOSITORY}/blob/{commit}/{path}"
    return f"{base}#L{line}" if line else base


def enrich_model(
    *,
    model_id: str,
    annotation: dict[str, Any],
    temporal_repo: Path,
    commit: str,
    evidence: dict[str, Any],
    dot_path: Path,
) -> dict[str, Any]:
    module = annotation["module"]
    module_rel = f"model/{module}.tla"
    config_rel = f"model/{module}.cfg"
    module_path = temporal_repo / module_rel
    config_path = temporal_repo / config_rel
    parsed_module = parse_module(module_path)
    parsed_config = parse_config(config_path)

    annotated_actions = set(annotation["actions"])
    next_actions = set(parsed_module["nextActions"])
    if annotated_actions != next_actions:
        raise RuntimeError(
            f"{module} action annotations drifted; missing={sorted(next_actions - annotated_actions)}, "
            f"extra={sorted(annotated_actions - next_actions)}"
        )
    for invariant in annotation["invariants"]:
        if invariant not in parsed_module["definitions"]:
            raise RuntimeError(f"{module} is missing annotated invariant {invariant}")
    configured_invariant = parsed_config["invariant"]
    configured_property = parsed_config["property"]
    for name in (configured_invariant, configured_property):
        if name not in parsed_module["definitions"]:
            raise RuntimeError(f"{module} config references unknown operator {name}")

    graph = parse_dot(dot_path, annotation["aggregation"])
    check = evidence["passing_models"][model_id]
    if graph["concreteStateCount"] != check["distinct_states"]:
        raise RuntimeError(
            f"{module} DOT states {graph['concreteStateCount']} != evidence "
            f"{check['distinct_states']}"
        )
    expected_transitions = check["generated_states"] - 1
    if graph["concreteTransitionCount"] != expected_transitions:
        raise RuntimeError(
            f"{module} DOT transitions {graph['concreteTransitionCount']} != "
            f"generated states - 1 ({expected_transitions})"
        )

    module_hash = sha256_path(module_path)
    config_hash = sha256_path(config_path)
    evidence_hashes = evidence["input_sha256"]
    if evidence_hashes.get(module_rel) != module_hash:
        raise RuntimeError(f"checked evidence does not bind current {module_rel}")
    if evidence_hashes.get(config_rel) != config_hash:
        raise RuntimeError(f"checked evidence does not bind current {config_rel}")

    for node in graph["nodes"]:
        state_annotation = annotation.get("states", {}).get(node["id"])
        if state_annotation:
            node.update(state_annotation)
        elif "label" not in node:
            node["label"] = node["id"]

    transition_rows = graph["transitions"]
    actions: list[dict[str, Any]] = []
    for action_name in parsed_module["nextActions"]:
        action_annotation = annotation["actions"][action_name]
        matching = [
            transition
            for transition in transition_rows
            if transition["action"] == action_name
            or transition["operator"] == action_name
        ]
        actions.append(
            {
                "id": action_name,
                "category": action_annotation["category"],
                "description": action_annotation["description"],
                "sourceLine": parsed_module["definitions"][action_name],
                "sourceUrl": source_url(
                    commit, module_rel, parsed_module["definitions"][action_name]
                ),
                "reachableInPrincipal": bool(matching),
                "concreteTransitionCount": sum(
                    transition["concreteTransitions"] for transition in matching
                ),
                "concreteLabels": sorted(
                    {transition["action"] for transition in matching}
                ),
            }
        )

    safety_components = [
        {
            "id": name,
            "description": description,
            "sourceLine": parsed_module["definitions"][name],
            "sourceUrl": source_url(
                commit, module_rel, parsed_module["definitions"][name]
            ),
        }
        for name, description in annotation["invariants"].items()
    ]

    curated: dict[str, Any]
    if "structure_nodes" in annotation:
        curated = {
            "kind": "scope_structure",
            "nodes": annotation["structure_nodes"],
            "edges": annotation["structure_edges"],
        }
    else:
        curated = {
            "kind": "state_action",
            "nodes": [
                {"id": state_id, **state}
                for state_id, state in annotation["states"].items()
            ],
            "edges": annotation["curated_edges"],
        }
    curated["label"] = "Curated explanatory structure"
    curated["disclaimer"] = (
        "Layout and prose are curated for explanation. Names are checked against "
        "the pinned module; this is not an automatic rendering of every TLA+ formula."
    )

    return {
        "id": model_id,
        "module": module,
        "title": annotation["title"],
        "shortTitle": annotation["short_title"],
        "eyebrow": annotation["eyebrow"],
        "summary": annotation["summary"],
        "question": annotation["question"],
        "source": {
            "modulePath": module_rel,
            "moduleSha256": module_hash,
            "moduleUrl": source_url(commit, module_rel),
            "configPath": config_rel,
            "configSha256": config_hash,
            "configUrl": source_url(commit, config_rel),
        },
        "variables": parsed_module["variables"],
        "constants": parsed_config["constants"],
        "actions": actions,
        "curated": curated,
        "scenarios": annotation["scenarios"],
        "safety": {
            "configuredInvariant": configured_invariant,
            "sourceLine": parsed_module["definitions"][configured_invariant],
            "sourceUrl": source_url(
                commit,
                module_rel,
                parsed_module["definitions"][configured_invariant],
            ),
            "components": safety_components,
        },
        "liveness": {
            "configuredProperty": configured_property,
            "description": annotation["property_description"],
            "sourceLine": parsed_module["definitions"][configured_property],
            "sourceUrl": source_url(
                commit,
                module_rel,
                parsed_module["definitions"][configured_property],
            ),
        },
        "check": {
            "status": check["status"],
            "generatedStates": check["generated_states"],
            "distinctStates": check["distinct_states"],
            "depth": check["depth"],
            "statesLeft": check["states_left"],
            "sanyStatus": evidence["sany"][model_id]["status"],
        },
        "stateSpace": {
            "kind": "complete_tlc_dot_aggregation",
            "label": annotation["aggregation"]["label"],
            "aggregation": annotation["aggregation"],
            "concreteStates": graph["concreteStateCount"],
            "concreteTransitions": graph["concreteTransitionCount"],
            "abstractStates": len(graph["nodes"]),
            "nodes": graph["nodes"],
            "transitions": transition_rows,
            "dotSha256": sha256_path(dot_path),
            "disclaimer": (
                "Counts and transitions are generated from TLC's complete DOT dump. "
                "States are collapsed only by the named aggregation variable(s); raw "
                "state values and the private DOT file are not published."
            ),
        },
    }


def build_projection(args: argparse.Namespace) -> dict[str, Any]:
    temporal_repo = args.temporal_repo.resolve()
    head, committed_at = verify_temporal_checkout(temporal_repo, args.allow_dirty)
    annotations = json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))
    evidence_path = temporal_repo / "evidence" / "model-check-summary.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    baseline = json.loads(
        (temporal_repo / "source" / "baseline.json").read_text(encoding="utf-8")
    )

    java_value = str(args.java)
    java = Path(shutil.which(java_value) or java_value).resolve()
    tla_jar = args.tla_jar.resolve()
    if not java.is_file() or not os.access(java, os.X_OK):
        raise RuntimeError(f"Java executable is unavailable: {java}")
    if not tla_jar.is_file():
        raise RuntimeError(f"TLA+ tools jar is unavailable: {tla_jar}")
    if sha256_path(tla_jar) != evidence["tooling"]["tla2tools_sha256"]:
        raise RuntimeError("TLA+ tools jar hash does not match checked evidence")

    models: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="chambers-tla-visualization-") as tmp:
        output_dir = Path(tmp)
        for model_id in MODEL_ORDER:
            annotation = annotations["models"][model_id]
            dot_path, _ = run_tlc_dump(
                java=java,
                tla_jar=tla_jar,
                temporal_repo=temporal_repo,
                module=annotation["module"],
                output_dir=output_dir,
            )
            models.append(
                enrich_model(
                    model_id=model_id,
                    annotation=annotation,
                    temporal_repo=temporal_repo,
                    commit=head,
                    evidence=evidence,
                    dot_path=dot_path,
                )
            )

    if git_value(temporal_repo, "status", "--porcelain") and not args.allow_dirty:
        raise RuntimeError("TLC projection unexpectedly modified the temporal checkout")

    negative_controls: list[dict[str, Any]] = []
    for control_id, annotation in annotations["negative_controls"].items():
        result = evidence["expected_counterexamples"].get(control_id)
        if result is None:
            raise RuntimeError(f"missing expected counterexample evidence: {control_id}")
        negative_controls.append(
            {
                "id": control_id,
                "model": annotation["model"],
                "title": annotation["title"],
                "description": annotation["description"],
                "status": result["status"],
                "violatedInvariant": result["invariant"],
                "generatedStates": result["generated_states"],
                "distinctStates": result["distinct_states"],
                "traceDepth": result["trace_depth"],
            }
        )

    return {
        "schema": "dreamcatcher.chambers-tla-model-projection/v1",
        "source": {
            "repository": EXPECTED_REPOSITORY,
            "visibility": "private",
            "commit": head,
            "committedAt": committed_at,
            "commitUrl": f"https://github.com/{EXPECTED_REPOSITORY}/tree/{head}",
            "evidencePath": "evidence/model-check-summary.json",
            "evidenceSha256": sha256_path(evidence_path),
            "evidenceGeneratedAtUtc": evidence["generated_at_utc"],
            "authority": {
                "repository": baseline["source"]["repository"],
                "commit": baseline["source"]["commit"],
                "path": baseline["source"]["path"],
                "sha256": baseline["source"]["sha256"],
            },
            "architectureSynthesis": {
                "name": baseline["architecture_synthesis"]["final_name"],
                "schema": baseline["architecture_synthesis"]["schema"],
                "digest": baseline["architecture_synthesis"]["model_digest"],
                "acceptedPartition": baseline["architecture_synthesis"][
                    "accepted_partition"
                ],
                "candidates": baseline["architecture_synthesis"]["bound"][
                    "candidates"
                ],
            },
        },
        "projection": {
            "annotationsSchema": annotations["schema"],
            "annotationsSha256": sha256_path(ANNOTATIONS_PATH),
            "disclosure": annotations["disclosure"],
            "boundary": (
                "Public-safe projection only: exact names, line anchors, hashes, bounded "
                "state/transition aggregates, and TLC receipts. It excludes raw private "
                "TLA+ source, concrete state labels, and raw DOT graphs."
            ),
        },
        "tooling": {
            "sany": evidence["tooling"]["sany"],
            "tlc": evidence["tooling"]["tlc"],
            "javaVersion": evidence["tooling"]["java_version"],
            "tla2toolsSha256": evidence["tooling"]["tla2tools_sha256"],
            "dotExport": "tlc2.TLC -dump dot,actionlabels,colorize",
            "workers": 1,
        },
        "totals": {
            "models": len(models),
            "generatedStates": sum(model["check"]["generatedStates"] for model in models),
            "distinctStates": sum(model["check"]["distinctStates"] for model in models),
            "dotTransitions": sum(
                model["stateSpace"]["concreteTransitions"] for model in models
            ),
            "expectedCounterexamples": len(negative_controls),
        },
        "models": models,
        "negativeControls": negative_controls,
        "explanation": {
            "curated": (
                "The Explain view is a deliberately curated map whose action and property "
                "names are checked against the pinned modules. It explains intent; it is not "
                "a full semantic derivation."
            ),
            "derived": (
                "The TLC State Space view is automatically aggregated from complete DOT dumps "
                "produced by a fresh TLC run and cross-checked against committed evidence counts."
            ),
            "proof": (
                "PASS receipts mean TLC found no violation within the configured finite bounds. "
                "Expected counterexamples prove that five deliberately weakened guards are "
                "observable. Neither result proves deployment conformance."
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("temporal_repo", type=Path)
    parser.add_argument("--java", type=Path, required=True)
    parser.add_argument("--tla-jar", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow a dirty temporal checkout (never use for a published projection).",
    )
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        projection = build_projection(args)
        rendered = json.dumps(projection, indent=2, ensure_ascii=False) + "\n"
        output = args.output.resolve()
        if args.check:
            if not output.is_file() or output.read_text(encoding="utf-8") != rendered:
                print(f"stale TLA+ projection: {output}", file=sys.stderr)
                return 1
            print(
                f"TLA+ projection current: {projection['totals']['distinctStates']} "
                f"distinct states, {projection['totals']['dotTransitions']} transitions"
            )
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        print(
            f"Wrote {output}: {projection['totals']['distinctStates']} distinct states, "
            f"{projection['totals']['dotTransitions']} transitions"
        )
        return 0
    except (OSError, RuntimeError, KeyError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
