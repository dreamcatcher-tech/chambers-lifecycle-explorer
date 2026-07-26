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
        cls.documents = {document["id"]: document for document in cls.payload["documents"]}

    def test_both_authoritative_documents_are_present(self) -> None:
        self.assertEqual({"chambers", "cardflow"}, set(self.documents))
        self.assertEqual("chambers", self.payload["defaultDocumentId"])

    def test_expected_sequence_surfaces_are_present(self) -> None:
        expected = {
            "chambers": {
                "activation-kernel",
                "host-activation",
                "candidate-formation",
                "fenced-development",
                "artifact-build",
                "attested-builds",
                "candidate-verification",
                "selection-rollback",
                "quiesce-wake",
            },
            "cardflow": {
                "register-claim",
                "queue-inspect-wait",
                "materialize-session",
                "continue-session",
                "renew-leases",
                "release-handoff",
                "cancel-expire",
                "recover-reconcile",
                "reject-bypass",
            },
        }
        for document_id, sequence_ids in expected.items():
            actual = {sequence["id"] for sequence in self.documents[document_id]["sequences"]}
            self.assertEqual(sequence_ids, actual)

    def test_every_arrow_resolves_to_its_document_function_table(self) -> None:
        for document in self.documents.values():
            functions = {function["id"] for function in document["functions"]}
            calls = [call for sequence in document["sequences"] for call in sequence["calls"]]
            self.assertTrue(calls)
            self.assertTrue(all(call["function"] in functions for call in calls))
            self.assertEqual(len(calls), sum(len(function["usages"]) for function in document["functions"]))

    def test_source_line_coordinates_point_to_exact_mermaid_content(self) -> None:
        for document in self.documents.values():
            lines = (ROOT / "source" / document["source"]["snapshotPath"]).read_text(encoding="utf-8").splitlines()
            for sequence in document["sequences"]:
                self.assertEqual("sequenceDiagram", lines[sequence["sourceLine"] - 1].strip())
                for call in sequence["calls"]:
                    source_line = lines[call["sourceLine"] - 1]
                    self.assertIn(call["function"], source_line, f"wrong source line for {document['id']}/{call['id']}")

    def test_document_counts_match_the_two_sources(self) -> None:
        chambers = self.documents["chambers"]["stats"]
        self.assertEqual((9, 76, 37, 60, 16), (
            chambers["sequences"], chambers["calls"], chambers["functions"],
            chambers["i3Calls"], chambers["hostCalls"],
        ))
        cardflow = self.documents["cardflow"]["stats"]
        self.assertEqual((9, 66, 33, 66, 0), (
            cardflow["sequences"], cardflow["calls"], cardflow["functions"],
            cardflow["i3Calls"], cardflow["hostCalls"],
        ))

    def test_host_boundary_is_explicit_and_chambers_only(self) -> None:
        chambers_host = {
            function["id"]
            for function in self.documents["chambers"]["functions"]
            if function["kind"] == "host"
        }
        self.assertEqual(
            {"wake_engine", "activate_chamber", "stop_chamber", "deliver_final_reply"},
            chambers_host,
        )
        self.assertTrue(all(function["kind"] == "i3" for function in self.documents["cardflow"]["functions"]))

    def test_chambers_display_starts_with_cold_engine_then_ordinary_activation(self) -> None:
        sequences = self.documents["chambers"]["sequences"]
        self.assertEqual(
            [("host-activation", "Engine cold start"), ("activation-kernel", "Ordinary activation")],
            [(sequence["id"], sequence["shortTitle"]) for sequence in sequences[:2]],
        )
        self.assertEqual(list(range(1, len(sequences) + 1)), [sequence["ordinal"] for sequence in sequences])

        host_calls = [call["function"] for call in sequences[0]["calls"]]
        ordinary_calls = [call["function"] for call in sequences[1]["calls"]]
        self.assertNotIn("filesystem::object::read", host_calls)
        self.assertIn("filesystem::object::read", ordinary_calls)
        self.assertIn("wake_engine", host_calls)

        ready_attest = sequences[0]["calls"][1]
        cold_activate = sequences[0]["calls"][2]
        self.assertFalse(any("Read current[engine]" in note["text"] for note in ready_attest["notes"]))
        self.assertTrue(any("Read current[engine]" in note["text"] for note in cold_activate["notes"]))

    def test_procman_and_physical_runtime_projection_preserve_authority_order(self) -> None:
        chambers = self.documents["chambers"]
        for sequence in chambers["sequences"]:
            participant_ids = [participant["id"] for participant in sequence["participants"]]
            if "procman" in participant_ids:
                self.assertEqual("procman", participant_ids[0], sequence["id"])
            physical = [
                call for call in sequence["calls"]
                if call["function"] in {"activate_chamber", "stop_chamber"}
            ]
            if physical:
                self.assertEqual(["procman", "Runtime"], participant_ids[:2], sequence["id"])
                self.assertTrue(all(call["from"] == "procman" and call["to"] == "Runtime" for call in physical))
                runtime = next(participant for participant in sequence["participants"] if participant["id"] == "Runtime")
                self.assertEqual("host", runtime["role"])

        functions = {function["id"]: function for function in chambers["functions"]}
        self.assertEqual("Trusted host runtime", functions["activate_chamber"]["owner"])
        self.assertEqual("Trusted host runtime", functions["stop_chamber"]["owner"])

    def test_sequence_actor_references_and_ids_are_sound_per_document(self) -> None:
        for document in self.documents.values():
            call_ids: set[str] = set()
            for sequence in document["sequences"]:
                actor_ids = {participant["id"] for participant in sequence["participants"]}
                self.assertGreaterEqual(len(actor_ids), 2)
                for call in sequence["calls"]:
                    self.assertIn(call["from"], actor_ids)
                    self.assertIn(call["to"], actor_ids)
                    self.assertNotIn(call["id"], call_ids)
                    call_ids.add(call["id"])

    def test_source_manifest_binds_both_exact_document_bytes(self) -> None:
        manifest = json.loads((ROOT / "source" / "manifest.json").read_text(encoding="utf-8"))
        manifest_documents = {document["id"]: document for document in manifest["documents"]}
        for document_id, document in self.documents.items():
            source = document["source"]
            manifest_source = manifest_documents[document_id]
            source_path = ROOT / "source" / manifest_source["snapshotPath"]
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            self.assertEqual(manifest_source["documentSha256"], digest)
            self.assertEqual(source["sourceCommit"], manifest_source["sourceCommit"])
            self.assertEqual(
                source["url"],
                f"https://github.com/{manifest['repository']}/blob/"
                f"{manifest_source['sourceCommit']}/{manifest_source['path']}",
            )

    def test_playback_has_branch_and_note_context_in_both_documents(self) -> None:
        for document in self.documents.values():
            calls = [call for sequence in document["sequences"] for call in sequence["calls"]]
            self.assertTrue(any(call["context"] for call in calls), document["id"])
            self.assertTrue(any(call["notes"] for call in calls), document["id"])

        cancel = next(
            sequence for sequence in self.documents["cardflow"]["sequences"]
            if sequence["id"] == "cancel-expire"
        )
        handoff_note = "Grant the next eligible waiter only after"
        self.assertFalse(any(handoff_note in note["text"] for note in cancel["calls"][2]["notes"]))
        self.assertTrue(any(handoff_note in note["text"] for note in cancel["calls"][-1]["notes"]))

    def test_cardflow_function_status_is_preserved(self) -> None:
        statuses = {function["implementationStatus"] for function in self.documents["cardflow"]["functions"]}
        self.assertIn("required", statuses)
        self.assertIn("contract-extension-required", statuses)
        self.assertIn("existing", statuses)

    def test_trace_interaction_contract_is_present(self) -> None:
        app = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="resetSequence"', html)
        self.assertIn('id="stickyActorHeader"', html)
        self.assertIn("scheduleVerticalCallReveal", app)
        self.assertIn("syncStickyActorHeader", app)
        self.assertIn("stabilizeCallInspectorHeight", app)
        self.assertIn("scheduleHistoryScrollSnapshot", app)
        self.assertIn("reconcileFilteredCallSelection", app)
        self.assertIn("sequenceFocusIdentity", app)
        self.assertIn('window.history.scrollRestoration = "manual"', app)
        self.assertIn("event.defaultPrevented", app)
        self.assertIn('window.history.pushState', app)
        self.assertIn('window.addEventListener("popstate"', app)
        self.assertEqual(1, app.count(".scrollIntoView("))
        self.assertIn("results[state.searchIndex].scrollIntoView", app)
        self.assertIn("overflow-y: clip", css)
        self.assertIn("overflow-anchor: none", css)
        self.assertIn("touch-action: pan-x pan-y", css)
        self.assertIn("height: var(--call-inspector-height", css)
        self.assertIn("call-function-meta", app)
        self.assertIn("call-function-meta", css)
        self.assertIn("note.context", app)
        self.assertIn("Outside conditional context", app)
        self.assertIn("rightCharacters", app)
        self.assertIn("kindWidth", app)
        self.assertNotIn('id="currentBranch"', html)
        self.assertNotIn("branch-chip", app)


if __name__ == "__main__":
    unittest.main()
