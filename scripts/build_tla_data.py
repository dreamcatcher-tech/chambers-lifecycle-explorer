#!/usr/bin/env python3
"""Build the browser bundle from the committed public TLA+ projection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source" / "tla-model-projection.json"
OUTPUT = ROOT / "site" / "tla" / "model-data.js"


def render() -> tuple[str, dict]:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if data.get("schema") != "dreamcatcher.chambers-tla-model-projection/v3":
        raise ValueError("unsupported TLA+ projection schema")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return (
        "// Generated from source/tla-model-projection.json. Do not edit.\n"
        f"window.CHAMBERS_TLA_MODEL = {payload};\n",
        data,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args()
    try:
        output, data = render()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != output:
            print(f"stale generated bundle: {OUTPUT}", file=sys.stderr)
            return 1
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(output, encoding="utf-8")

    if args.print_summary:
        totals = data["totals"]
        verb = "Verified" if args.check else "Built"
        print(
            f"{verb} TLA+ browser data: {totals['models']} models, "
            f"{totals['distinctStates']} distinct TLC states, "
            f"{totals['dotTransitions']} transitions, "
            f"{totals['expectedCounterexamples']} expected counterexamples"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
