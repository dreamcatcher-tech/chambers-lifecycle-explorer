from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_data", ROOT / "scripts" / "build_data.py")
build_data = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(build_data)


class BuildDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = build_data.build_payload()

    def test_expected_sequence_surface_is_present(self) -> None:
        expected = {
            "activation-kernel",
            "host-activation",
            "candidate-formation",
            "fenced-development",
            "artifact-build",
            "attested-builds",
            "candidate-verification",
            "selection-rollback",
            "quiesce-wake",
        }
        actual = {sequence["id"] for sequence in self.payload["sequences"]}
        self.assertEqual(expected, actual)

    def test_every_arrow_resolves_to_the_function_table(self) -> None:
        functions = {function["id"] for function in self.payload["functions"]}
        calls = [call for sequence in self.payload["sequences"] for call in sequence["calls"]]
        self.assertTrue(calls)
        self.assertTrue(all(call["function"] in functions for call in calls))
        self.assertEqual(len(calls), sum(len(function["usages"]) for function in self.payload["functions"]))

    def test_host_boundary_is_explicit_and_small(self) -> None:
        host_functions = {function["id"] for function in self.payload["functions"] if function["kind"] == "host"}
        self.assertEqual(
            {"wake_engine", "activate_chamber", "stop_chamber", "deliver_final_reply"},
            host_functions,
        )
        host_calls = [
            call
            for sequence in self.payload["sequences"]
            for call in sequence["calls"]
            if call["kind"] == "host"
        ]
        self.assertTrue(host_calls)
        self.assertTrue(all(call["function"] in host_functions for call in host_calls))

    def test_sequence_actor_references_and_ids_are_sound(self) -> None:
        call_ids: set[str] = set()
        for sequence in self.payload["sequences"]:
            actor_ids = {participant["id"] for participant in sequence["participants"]}
            self.assertGreaterEqual(len(actor_ids), 3)
            for call in sequence["calls"]:
                self.assertIn(call["from"], actor_ids)
                self.assertIn(call["to"], actor_ids)
                self.assertNotIn(call["id"], call_ids)
                call_ids.add(call["id"])

    def test_source_metadata_binds_exact_document_bytes(self) -> None:
        source = ROOT / "source" / "chambers-lifecycle-sequences.md"
        metadata = json.loads((ROOT / "source" / "metadata.json").read_text(encoding="utf-8"))
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(metadata["documentSha256"], digest)
        self.assertEqual(self.payload["source"]["sourceCommit"], metadata["sourceCommit"])

    def test_playback_has_branch_and_note_context(self) -> None:
        calls = [call for sequence in self.payload["sequences"] for call in sequence["calls"]]
        self.assertTrue(any(call["context"] for call in calls))
        self.assertTrue(any(call["notes"] for call in calls))


if __name__ == "__main__":
    unittest.main()
