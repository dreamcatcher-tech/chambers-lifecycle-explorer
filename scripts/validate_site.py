#!/usr/bin/env python3
"""Deterministic publication checks for the Chambers Atlas static site."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class SiteParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.attributes_by_id: dict[str, dict[str, str | None]] = {}
        self.asset_urls: list[str] = []
        self.has_viewport = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
            self.attributes_by_id[values["id"] or ""] = values
        if tag == "meta" and values.get("name") == "viewport":
            self.has_viewport = True
        for key in ("src", "href"):
            value = values.get(key)
            if value:
                self.asset_urls.append(value)


def load_builder():
    spec = importlib.util.spec_from_file_location("build_data", ROOT / "scripts" / "build_data.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def main() -> int:
    failures: list[str] = []
    required_files = [
        SITE / "index.html",
        SITE / "styles.css",
        SITE / "app.js",
        SITE / "data.js",
        SITE / ".nojekyll",
        ROOT / "source" / "chambers-lifecycle-sequences.md",
        ROOT / "source" / "metadata.json",
        ROOT / ".github" / "workflows" / "pages.yml",
    ]
    for path in required_files:
        if not path.exists():
            fail(f"missing required file: {path.relative_to(ROOT)}", failures)

    if failures:
        print("FAIL: " + "; ".join(failures), file=sys.stderr)
        return 1

    builder = load_builder()
    try:
        payload = builder.build_payload()
        expected_bundle = builder.render_bundle(payload)
    except Exception as exc:  # validator should report parser errors as one concise failure
        fail(f"source parser failed: {exc}", failures)
        payload = None
        expected_bundle = ""

    actual_bundle = (SITE / "data.js").read_text(encoding="utf-8")
    if expected_bundle and actual_bundle != expected_bundle:
        fail("site/data.js is stale", failures)

    html = (SITE / "index.html").read_text(encoding="utf-8")
    css = (SITE / "styles.css").read_text(encoding="utf-8")
    javascript = (SITE / "app.js").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    parser = SiteParser()
    parser.feed(html)
    required_ids = {
        "journeyList", "mobileSceneSelect", "traceView", "mapView", "functionsView",
        "sequenceSvg", "mapSvg", "callInspector", "functionList", "functionDetail",
        "playPause", "previousCall", "nextCall", "stepScrubber", "actorFilter",
        "searchDialog", "helpDialog", "sourceDocumentLink", "footerSource",
    }
    missing_ids = required_ids - parser.ids
    if missing_ids:
        fail(f"index.html missing UI ids: {sorted(missing_ids)}", failures)
    if not parser.has_viewport:
        fail("index.html has no viewport meta tag", failures)
    for source_link_id in ("sourceDocumentLink", "footerSource"):
        source_link = parser.attributes_by_id.get(source_link_id, {})
        if source_link.get("target") != "_blank" or "noopener" not in (source_link.get("rel") or ""):
            fail(f"{source_link_id} must open safely in a new page", failures)
    external_assets = [url for url in parser.asset_urls if url.startswith(("http://", "https://", "//"))]
    if external_assets:
        fail(f"site is not self-contained; external assets: {external_assets}", failures)

    for breakpoint in ("max-width: 1040px", "max-width: 560px"):
        if breakpoint not in css:
            fail(f"styles.css missing responsive breakpoint {breakpoint}", failures)
    if "prefers-reduced-motion: reduce" not in css:
        fail("styles.css missing reduced-motion handling", failures)
    if "overflow-x: hidden" not in css:
        fail("styles.css missing page-level horizontal overflow guard", failures)

    expected_behaviors = [
        "startPlayback", "renderSequenceSvg", "renderMap", "renderFunctionCatalog",
        "touchstart", "navigator.clipboard", "URLSearchParams", "setActorFilter",
        "sourceDocumentLink.href = source.url", "footerSource.href = source.url",
    ]
    for behavior in expected_behaviors:
        if behavior not in javascript:
            fail(f"app.js missing required behavior marker: {behavior}", failures)

    for marker in ("actions/configure-pages@", "actions/upload-pages-artifact@", "actions/deploy-pages@", "python3 scripts/validate_site.py"):
        if marker not in workflow:
            fail(f"Pages workflow missing: {marker}", failures)

    secret_patterns = {
        "GitHub classic token": r"gh[pousr]_[A-Za-z0-9]{20,}",
        "GitHub fine-grained token": r"github_pat_[A-Za-z0-9_]{20,}",
        "generic private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    }
    public_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in [SITE / "index.html", SITE / "styles.css", SITE / "app.js", SITE / "data.js"]
    )
    for label, pattern in secret_patterns.items():
        if re.search(pattern, public_text):
            fail(f"possible {label} in public site", failures)

    node_check = subprocess.run(
        ["node", "--check", str(SITE / "app.js")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if node_check.returncode:
        fail(f"node --check failed: {node_check.stderr.strip()}", failures)

    if payload:
        if payload["stats"]["sequences"] < 9:
            fail("fewer than nine lifecycle sequences were generated", failures)
        if payload["stats"]["hostCalls"] < 1 or payload["stats"]["i3Calls"] < 1:
            fail("generated data does not distinguish both I3 and host calls", failures)
        if payload["stats"]["usedFunctions"] >= payload["stats"]["functions"]:
            fail("function catalog no longer demonstrates defined-but-not-pictured coverage", failures)

    if failures:
        print("FAIL")
        for item in failures:
            print(f" - {item}")
        return 1

    stats = payload["stats"]
    print(
        "PASS: self-contained site · fresh source bundle · "
        f"{stats['sequences']} sequences · {stats['calls']} calls · "
        f"{stats['functions']} functions · responsive + Pages workflow present"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
