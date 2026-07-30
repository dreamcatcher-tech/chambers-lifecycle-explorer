#!/usr/bin/env python3
"""Validate the TLA+ model explorer and its public projection contract."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
TLA_SITE = SITE / "tla"
SOURCE = ROOT / "source" / "tla-model-projection.json"
ANNOTATIONS = ROOT / "scripts" / "tla_model_annotations.json"
BUNDLE = TLA_SITE / "model-data.js"


class DocumentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []
        self.assets: list[str] = []
        self.scripts: list[str] = []
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.append(values["id"] or "")
        if tag == "script" and values.get("src"):
            self.scripts.append(values["src"] or "")
            self.assets.append(values["src"] or "")
        if tag == "link" and values.get("href"):
            self.assets.append(values["href"] or "")
        if tag == "a" and values.get("href"):
            self.links.append(values["href"] or "")


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load_bundle() -> dict:
    marker = "window.CHAMBERS_TLA_MODEL = "
    text = BUNDLE.read_text(encoding="utf-8")
    if marker not in text or not text.rstrip().endswith(";"):
        fail("model-data.js is not the expected assignment")
    payload = text.split(marker, 1)[1].rstrip()[:-1]
    return json.loads(payload)


def validate_required_files() -> None:
    required = [
        SOURCE,
        ANNOTATIONS,
        ROOT / "scripts" / "sync_tla_visualization.py",
        ROOT / "scripts" / "build_tla_data.py",
        TLA_SITE / "index.html",
        TLA_SITE / "styles.css",
        TLA_SITE / "app.js",
        BUNDLE,
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        fail(f"missing TLA+ explorer files: {', '.join(missing)}")


def validate_projection(payload: dict) -> None:
    if payload.get("schema") != "dreamcatcher.chambers-tla-model-projection/v3":
        fail("unexpected TLA+ projection schema")
    source = payload.get("source", {})
    if source.get("repository") != "dreamcatcher-tech/chambers-temporal-model":
        fail("projection is not bound to the temporal-model repository")
    if source.get("visibility") != "private":
        fail("private temporal source disclosure is missing")
    if not re.fullmatch(r"[0-9a-f]{40}", source.get("commit", "")):
        fail("temporal source commit is not a full SHA")
    for key in ("evidenceSha256",):
        if not re.fullmatch(r"[0-9a-f]{64}", source.get(key, "")):
            fail(f"invalid source receipt hash: {key}")
    authority = source.get("authority", {})
    if authority.get("repository") != "dreamcatcher-tech/chambers-temporal-model":
        fail("projection authority is not the temporal-model release")
    if authority.get("commit") != source.get("commit"):
        fail("formal release commit does not match projected source commit")
    if authority.get("gitTag") != "formal-spec-v1.0.0":
        fail("formal release tag drifted")
    if not re.fullmatch(r"[0-9a-f]{64}", authority.get("manifestSha256", "")):
        fail("formal release manifest receipt is invalid")
    coverage = payload.get("projection", {}).get("coverage", {})
    if coverage.get("status") != "deliberately_bounded_public_subset":
        fail("public model coverage boundary is missing")
    if len(coverage.get("releaseKernels", [])) != 7:
        fail("formal release kernel inventory is incomplete")

    models = payload.get("models", [])
    if [model.get("id") for model in models] != [
        "ark_core_appliance", "multi_ark", "host_cutover"
    ]:
        fail("model registry/order drifted")

    generated_total = 0
    distinct_total = 0
    transition_total = 0
    properties_by_model: dict[str, set[str]] = {}
    for model in models:
        model_id = model["id"]
        check = model["check"]
        if check.get("status") != "pass" or check.get("sanyStatus") != "pass":
            fail(f"{model_id} does not carry passing SANY/TLC evidence")
        if check.get("statesLeft") != 0:
            fail(f"{model_id} left states unchecked")
        generated_total += check["generatedStates"]
        distinct_total += check["distinctStates"]

        model_source = model["source"]
        for key in ("moduleSha256", "configSha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", model_source.get(key, "")):
                fail(f"{model_id} has invalid {key}")
        if source["commit"] not in model_source.get("moduleUrl", ""):
            fail(f"{model_id} source URL is not commit pinned")

        action_ids = [action["id"] for action in model.get("actions", [])]
        if len(action_ids) != len(set(action_ids)) or not action_ids:
            fail(f"{model_id} has duplicate or empty actions")
        for action in model["actions"]:
            if action.get("sourceLine", 0) <= 0:
                fail(f"{model_id}/{action['id']} has no source line")
            if source["commit"] not in action.get("sourceUrl", ""):
                fail(f"{model_id}/{action['id']} source URL is not pinned")
            if action.get("concreteTransitionCount", 0) < 0:
                fail(f"{model_id}/{action['id']} has an invalid transition count")

        space = model["stateSpace"]
        if space.get("kind") != "complete_tlc_dot_aggregation":
            fail(f"{model_id} is not marked as a complete TLC aggregation")
        if space["concreteStates"] != check["distinctStates"]:
            fail(f"{model_id} state count does not match evidence")
        if space["concreteTransitions"] != check["generatedStates"] - 1:
            fail(f"{model_id} transition count does not match TLC generation count")
        if space["abstractStates"] != len(space["nodes"]):
            fail(f"{model_id} abstract state count drifted")
        if sum(node["concreteStates"] for node in space["nodes"]) != space["concreteStates"]:
            fail(f"{model_id} aggregate nodes do not cover every concrete state")
        if sum(row["concreteTransitions"] for row in space["transitions"]) != space["concreteTransitions"]:
            fail(f"{model_id} aggregate transitions do not cover every TLC transition")
        if not re.fullmatch(r"[0-9a-f]{64}", space.get("aggregateSha256", "")):
            fail(f"{model_id} aggregate receipt is invalid")
        transition_total += space["concreteTransitions"]

        curated = model["curated"]
        curated_ids = {node["id"] for node in curated["nodes"]}
        if len(curated_ids) != len(curated["nodes"]):
            fail(f"{model_id} curated nodes are duplicated")
        if (
            curated["kind"] == "state_action"
            and space["aggregation"]["kind"] == "scalar"
        ):
            aggregate_ids = {node["id"] for node in space["nodes"]}
            if not curated_ids <= aggregate_ids:
                fail(f"{model_id} curated state has no TLC aggregate")
        for edge in curated["edges"]:
            if edge["from"] not in curated_ids or edge["to"] not in curated_ids:
                fail(f"{model_id} curated edge has an unknown endpoint")
            for action in edge.get("actions", []):
                if action not in action_ids:
                    fail(f"{model_id} curated edge references unknown action {action}")
        for scenario in model["scenarios"]:
            if not scenario.get("steps"):
                fail(f"{model_id} has an empty scenario")
            for action in scenario["steps"]:
                if action not in action_ids:
                    fail(f"{model_id} scenario references unknown action {action}")

        properties = {item["id"] for item in model["safety"]["components"]}
        properties.add(model["safety"]["configuredInvariant"])
        properties.add(model["liveness"]["configuredProperty"])
        properties_by_model[model_id] = properties

    totals = payload["totals"]
    expected_totals = {
        "models": len(models),
        "generatedStates": generated_total,
        "distinctStates": distinct_total,
        "dotTransitions": transition_total,
        "expectedCounterexamples": len(payload["negativeControls"]),
    }
    if totals != expected_totals:
        fail(f"projection totals drifted: expected {expected_totals}, got {totals}")

    controls = payload["negativeControls"]
    if len(controls) != 8 or any(control.get("status") != "expected_counterexample" for control in controls):
        fail("expected-counterexample receipt set is incomplete")
    for control in controls:
        if control["violatedInvariant"] not in properties_by_model[control["model"]]:
            fail(f"counterexample {control['id']} references an unknown invariant")
        if control.get("traceDepth", 0) <= 0:
            fail(f"counterexample {control['id']} has no real trace depth")

    serialized = json.dumps(payload)
    for forbidden in ("UNCHANGED <<", "VARIABLES\\n", "/\\\\ roleReady =", "productionWriters = {"):
        if forbidden in serialized:
            fail(f"raw private model/state content leaked into projection: {forbidden}")


def validate_html_and_assets() -> None:
    html_text = (TLA_SITE / "index.html").read_text(encoding="utf-8")
    parser = DocumentParser()
    parser.feed(html_text)
    duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
    if duplicates:
        fail(f"duplicate IDs in TLA+ page: {', '.join(duplicates)}")
    required_ids = {
        "modelSwitcher", "modelTitle", "heroReceipt", "viewTabs", "modelSvg",
        "propertiesView", "scenarioSelect", "scenarioPlay", "inspectorTitle",
        "actionGrid", "receiptCommit", "receiptSourceLink",
    }
    missing = sorted(required_ids - set(parser.ids))
    if missing:
        fail(f"TLA+ page is missing required IDs: {', '.join(missing)}")
    if parser.scripts != ["./model-data.js", "./app.js"]:
        fail("TLA+ generated data must load before the application")
    for asset in parser.assets:
        if asset.startswith(("http://", "https://", "//")):
            fail(f"TLA+ page has an external runtime asset: {asset}")
        resolved = (TLA_SITE / asset).resolve()
        if not resolved.is_file():
            fail(f"TLA+ page references missing asset: {asset}")

    root_html = (SITE / "index.html").read_text(encoding="utf-8")
    if 'href="./tla/"' not in root_html or "TLA+ Model" not in root_html:
        fail("Lifecycle Atlas does not link to the TLA+ explorer")

    css = (TLA_SITE / "styles.css").read_text(encoding="utf-8")
    app = (TLA_SITE / "app.js").read_text(encoding="utf-8")
    for marker in (
        "@media (max-width: 880px)",
        "@media (max-width: 620px)",
        "prefers-reduced-motion",
        ".phase-dot",
        ".property-list",
    ):
        if marker not in css:
            fail(f"TLA+ CSS is missing responsive/accessibility marker: {marker}")
    for marker in (
        "renderExplainGraph",
        "renderTupleMatrix",
        "renderProperties",
        'toggleAttribute("hidden", hidden)',
        "complete TLC states",
        "popstate",
        "aria-label",
    ):
        if marker not in app:
            fail(f"TLA+ app is missing interaction marker: {marker}")
    if "innerHTML" in app:
        fail("TLA+ app must not inject generated content via innerHTML")


def run_generated_check() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_tla_data.py"), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        fail("generated TLA+ browser bundle is stale")


def run_javascript_check() -> None:
    node = shutil.which("node")
    if not node:
        print("WARN: node unavailable; JavaScript syntax check skipped")
        return
    for path in (TLA_SITE / "model-data.js", TLA_SITE / "app.js"):
        result = subprocess.run([node, "--check", str(path)], text=True, capture_output=True)
        if result.returncode:
            sys.stderr.write(result.stdout)
            sys.stderr.write(result.stderr)
            fail(f"JavaScript syntax failed: {path.relative_to(ROOT)}")


def main() -> None:
    validate_required_files()
    run_generated_check()
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    if load_bundle() != payload:
        fail("browser bundle payload differs from committed public projection")
    validate_projection(payload)
    validate_html_and_assets()
    run_javascript_check()
    print(
        "PASS: TLA+ source binding, complete TLC aggregates, curated map, "
        "counterexample receipts, responsive shell, and generated bundle are valid"
    )


if __name__ == "__main__":
    main()
