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
                "core-installation",
                "host-activation",
                "core-bootstrap",
                "core-reboot",
                "candidate-formation",
                "fenced-development",
                "artifact-build",
                "attested-builds",
                "candidate-verification",
                "selection-rollback",
                "core-cutover",
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
        self.assertEqual((13, 170, 50, 119, 51, 53), (
            chambers["sequences"], chambers["calls"], chambers["functions"],
            chambers["i3Calls"], chambers["hostCalls"], chambers["dictionaryTerms"],
        ))
        cardflow = self.documents["cardflow"]["stats"]
        self.assertEqual((9, 66, 33, 66, 0, 30), (
            cardflow["sequences"], cardflow["calls"], cardflow["functions"],
            cardflow["i3Calls"], cardflow["hostCalls"], cardflow["dictionaryTerms"],
        ))
        self.assertEqual(83, self.payload["stats"]["dictionaryTerms"])

    def test_host_boundary_is_explicit_and_chambers_only(self) -> None:
        chambers_host = {
            function["id"]
            for function in self.documents["chambers"]["functions"]
            if function["kind"] == "host"
        }
        self.assertEqual(
            {
                "install_boot_seed", "wake_bootset", "deliver_final_reply", "containerd_import",
                "containerd_resolve", "containerd_tag_update", "containerd_task_start",
                "containerd_task_stop",
            },
            chambers_host,
        )
        self.assertTrue(all(function["kind"] == "i3" for function in self.documents["cardflow"]["functions"]))

    def test_chambers_display_starts_with_genesis_bootstrap_reboot_then_ordinary_activation(self) -> None:
        sequences = self.documents["chambers"]["sequences"]
        self.assertEqual(
            [
                ("core-installation", "First boot installation"),
                ("host-activation", "Selected Boot set cold start"),
                ("core-bootstrap", "Boot control bootstrap"),
                ("core-reboot", "Reboot selected Boot set"),
                ("activation-kernel", "Ordinary activation"),
            ],
            [(sequence["id"], sequence["shortTitle"]) for sequence in sequences[:5]],
        )
        self.assertEqual(list(range(1, len(sequences) + 1)), [sequence["ordinal"] for sequence in sequences])

        by_id = {sequence["id"]: sequence for sequence in sequences}
        installation_calls = [call["function"] for call in by_id["core-installation"]["calls"]]
        host_calls = [call["function"] for call in by_id["host-activation"]["calls"]]
        core_calls = [call["function"] for call in by_id["core-bootstrap"]["calls"]]
        reboot_calls = [call["function"] for call in by_id["core-reboot"]["calls"]]
        ordinary_calls = [call["function"] for call in by_id["activation-kernel"]["calls"]]
        self.assertIn("containerd_import", installation_calls)
        self.assertIn("containerd_tag_update", installation_calls)
        self.assertNotIn("persistence::realization::read", host_calls)
        self.assertEqual(2, core_calls.count("routing::authenticate"))
        self.assertEqual(2, core_calls.count("routing::authorize_registration"))
        self.assertIn("persistence::routing::read", core_calls)
        self.assertIn("routing::reconcile", core_calls)
        self.assertNotIn("persistence::realization::read", reboot_calls)
        self.assertIn("persistence::realization::read", ordinary_calls)
        self.assertIn("chamber::activate", ordinary_calls)
        self.assertIn("wake_bootset", host_calls)
        self.assertNotIn("engine::identity::attest", host_calls)
        self.assertEqual(4, host_calls.count("containerd_task_start"))

        cold_starts = [call for call in by_id["host-activation"]["calls"] if call["function"] == "containerd_task_start"]
        labels = {context["label"] for call in cold_starts for context in call["context"]}
        branches = {context["branch"] for call in cold_starts for context in call["context"]}
        self.assertIn("No matching ready Engine task exists", labels)
        self.assertIn("No matching ready Router task exists", labels)
        self.assertIn("No matching ready Persistence task exists", labels)
        self.assertIn("No matching ready Supervisor task exists", labels)
        self.assertIn("Exact selected closures are retained", branches)

    def test_host_agent_and_containerd_projection_preserve_authority_order(self) -> None:
        chambers = self.documents["chambers"]
        for sequence in chambers["sequences"]:
            participant_ids = [participant["id"] for participant in sequence["participants"]]
            if "HostAgent" in participant_ids:
                self.assertEqual("HostAgent", participant_ids[0], sequence["id"])
            for call in sequence["calls"]:
                if call["to"] == "containerd":
                    self.assertEqual("HostAgent", call["from"], sequence["id"])
                    self.assertTrue(call["function"].startswith("containerd_"), sequence["id"])
                self.assertNotEqual("containerd", call["from"], sequence["id"])
            self.assertNotIn("Runtime", participant_ids)
            self.assertNotIn("Materializer", participant_ids)
            self.assertNotIn("procman", participant_ids)

        host_activation = next(sequence for sequence in chambers["sequences"] if sequence["id"] == "host-activation")
        roles = {participant["id"]: participant["role"] for participant in host_activation["participants"]}
        self.assertEqual("host", roles["HostAgent"])
        self.assertEqual("host", roles["containerd"])

        functions = {function["id"]: function for function in chambers["functions"]}
        self.assertEqual("Host Agent", functions["chamber::activate"]["owner"])
        self.assertEqual("Host Agent", functions["chamber::stop"]["owner"])
        self.assertEqual("Host Agent", functions["bootset::select"]["owner"])
        self.assertEqual("containerd and boot members", functions["containerd_task_start"]["owner"])
        self.assertEqual("Router", functions["routing::reconcile"]["owner"])

    def test_protected_boot_and_reconstructable_runtime_semantics_survive_projection(self) -> None:
        chambers = self.documents["chambers"]
        snapshot = (ROOT / "source" / chambers["source"]["snapshotPath"]).read_text(encoding="utf-8")
        self.assertNotIn("Filesystem Service", snapshot)
        self.assertNotIn("filesystem::", snapshot)
        self.assertIn("containerd boot namespace = product-durable Boot-set state", snapshot)
        self.assertIn("containerd ordinary runtime namespace = reconstructable", snapshot)
        self.assertIn("containerd state directory = volatile runtime state", snapshot)
        self.assertIn("only containerd client and the only writer", snapshot)

        persistence_roles = {
            participant["role"]
            for sequence in chambers["sequences"]
            for participant in sequence["participants"]
            if participant["id"] == "Persistence"
        }
        self.assertEqual({"resource"}, persistence_roles)
        self.assertFalse(
            any(
                participant["id"] == "Boot"
                for sequence in chambers["sequences"]
                for participant in sequence["participants"]
            )
        )

        calls = [call for sequence in chambers["sequences"] for call in sequence["calls"]]
        self.assertFalse(any(call["from"] == "containerd" for call in calls))
        self.assertFalse(
            any({call["from"], call["to"]} == {"containerd", "Persistence"} for call in calls)
        )
        build = next(sequence for sequence in chambers["sequences"] if sequence["id"] == "artifact-build")
        self.assertNotIn("containerd", {participant["id"] for participant in build["participants"]})
        self.assertIn("persistence::build::record", [call["function"] for call in build["calls"]])

    def test_engine_first_bootset_and_cutover_authority_survive_projection(self) -> None:
        chambers = self.documents["chambers"]
        snapshot = (ROOT / "source" / chambers["source"]["snapshotPath"]).read_text(encoding="utf-8")
        self.assertIn("dreamcatcher/bootset:current", snapshot)
        self.assertIn("Selection uses one image-record mutation over the coherent quartet", snapshot)
        self.assertIn("A crash before the image-record update leaves the complete predecessor selected", snapshot)
        self.assertIn("Builder remains outside every boot Chamber", snapshot)
        self.assertIn("Router and Supervisor are the mutual live-upgrade pair", snapshot)

        sequences = {sequence["id"]: sequence for sequence in chambers["sequences"]}
        reboot = sequences["core-reboot"]
        reboot_functions = [call["function"] for call in reboot["calls"]]
        self.assertEqual(4, reboot_functions.count("containerd_task_start"))
        self.assertNotIn("containerd_import", reboot_functions)
        self.assertNotIn("artifact::build", reboot_functions)

        selection = sequences["selection-rollback"]
        functions = [call["function"] for call in selection["calls"]]
        self.assertLess(functions.index("bootset::stage"), functions.index("bootset::select"))
        tag_update = next(call for call in selection["calls"] if call["function"] == "containerd_tag_update")
        self.assertEqual(("HostAgent", "containerd"), (tag_update["from"], tag_update["to"]))

        cutover_functions = [call["function"] for call in sequences["core-cutover"]["calls"]]
        self.assertLess(cutover_functions.index("containerd_tag_update"), cutover_functions.index("routing::inspect"))
        self.assertEqual(12, cutover_functions.count("containerd_task_start"))
        self.assertEqual(4, cutover_functions.count("containerd_tag_update"))
        self.assertIn("routing::claim", cutover_functions)
        self.assertIn("persistence::routing::prepare", cutover_functions)

    def test_mutual_router_supervisor_handover_context_survives_projection(self) -> None:
        chambers = self.documents["chambers"]
        cutover = next(sequence for sequence in chambers["sequences"] if sequence["id"] == "core-cutover")
        participants = {participant["id"]: participant["role"] for participant in cutover["participants"]}
        self.assertEqual("control", participants["Router"])
        self.assertEqual("control", participants["NextRouter"])
        self.assertEqual("control", participants["Supervisor"])
        self.assertEqual("resource", participants["Persistence"])

        branch_of = lambda call: {context["branch"] for context in call["context"]}
        claim_index, claim = next(
            (index, call) for index, call in enumerate(cutover["calls"])
            if call["function"] == "routing::claim"
        )
        router_branch = "Same Engine and only Router changes"
        self.assertIn(router_branch, branch_of(claim))
        predecessor_stop_index, predecessor_stop = next(
            (index, call) for index, call in enumerate(cutover["calls"])
            if call["function"] == "containerd_task_stop"
            and router_branch in branch_of(call)
            and any("task fencing, not route selection" in note["text"] for note in call["notes"])
        )
        self.assertLess(predecessor_stop_index, claim_index)

        completed_branches = {
            branch
            for call in cutover["calls"] if call["function"] == "persistence::routing::complete"
            for branch in branch_of(call)
        }
        self.assertEqual(
            {
                "Same Engine and only Supervisor changes",
                "Same Engine and only Router changes",
                "Same Engine and only Persistence changes",
                "Successor changes the Bootstrap Engine Realization",
            },
            completed_branches,
        )

        forbidden = {"routing::reconcile", "routing::fence", "routing::install", "routing::reopen", "routing::claim"}
        self.assertFalse(any(call["from"] == "HostAgent" and call["function"] in forbidden for call in cutover["calls"]))

    def test_break_and_else_note_contexts_are_preserved(self) -> None:
        registry = {
            "test::go": {
                "id": "test::go",
                "owner": "Test",
                "path": "I3",
                "kind": "i3",
                "implementationStatus": "unmarked",
                "contract": "Exercise parser context.",
                "sourceLine": 1,
                "usages": [],
            }
        }
        block = [
            (1, "sequenceDiagram"),
            (2, "participant A"),
            (3, "participant B"),
            (4, "alt Exact runtime is ready"),
            (5, "A->>B: `test::go`"),
            (6, "else Exact runtime is unavailable"),
            (7, "Note over A: Fail closed"),
            (8, "end"),
            (9, "break Exact runtime is unavailable"),
            (10, "Note over A: Terminalize this attempt"),
            (11, "end"),
            (12, "A->>B: `test::go`"),
        ]
        sequence = build_data.parse_mermaid_sequence(
            block,
            "Context fixture",
            registry,
            1,
            {"Context fixture": {"id": "context-fixture"}},
        )
        notes = [note for call in sequence["calls"] for note in call["notes"]]
        contexts = [context for note in notes for context in note["context"]]
        self.assertTrue(any(context["type"] == "alt" and context["branch"] == "Exact runtime is unavailable" for context in contexts))
        self.assertTrue(any(context["type"] == "break" and context["branch"] == "Exact runtime is unavailable" for context in contexts))
        self.assertFalse(sequence["calls"][-1]["context"])

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

    def test_dictionary_projection_is_source_exact_and_crosslinked(self) -> None:
        for document in self.documents.values():
            dictionary = document["dictionary"]
            ids = {entry["id"] for entry in dictionary}
            terms = [entry["term"] for entry in dictionary]
            lines = (ROOT / "source" / document["source"]["snapshotPath"]).read_text(encoding="utf-8").splitlines()
            self.assertEqual(terms, sorted(terms, key=str.casefold))
            self.assertEqual(len(dictionary), document["stats"]["dictionaryTerms"])
            self.assertEqual(len(ids), len(dictionary))
            for entry in dictionary:
                self.assertTrue(entry["definition"])
                self.assertTrue(set(entry["related"]).issubset(ids), entry["term"])
                self.assertTrue(lines[entry["sourceLine"] - 1].startswith(f"| {entry['term']} |"))

        chambers = {entry["id"]: entry for entry in self.documents["chambers"]["dictionary"]}
        self.assertIn("not an alias for Realization", chambers["covenant-lock"]["definition"])
        self.assertIn("Covenant lock plus one normalized launch specification", chambers["realization"]["definition"])
        self.assertIn("boot-set-selection", chambers["boot-set"]["related"])
        self.assertIn("bootstrap-engine-covenant", chambers["boot-set"]["related"])
        self.assertIn("router-covenant", chambers["boot-set"]["related"])
        self.assertIn("persistence-covenant", chambers["boot-set"]["related"])
        self.assertIn("supervisor-covenant", chambers["boot-set"]["related"])

        cardflow = {entry["id"]: entry for entry in self.documents["cardflow"]["dictionary"]}
        self.assertIn("Chambers-defined immutable executable lifecycle identity", cardflow["realization"]["definition"])

    def test_dictionary_parser_fails_closed_on_unknown_related_term(self) -> None:
        lines = [
            "## Dictionary",
            "",
            "| Term | Definition | Related terms |",
            "| --- | --- | --- |",
            "| Alpha | A sufficiently explicit canonical definition. | Missing |",
            "",
            "## Next section",
        ]
        with self.assertRaisesRegex(ValueError, "unknown related terms"):
            build_data.parse_dictionary(lines)

    def test_trace_interaction_contract_is_present(self) -> None:
        app = (ROOT / "site" / "app.js").read_text(encoding="utf-8")
        css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="resetSequence"', html)
        self.assertIn('id="stickyActorHeader"', html)
        self.assertIn("scheduleVerticalCallReveal", app)
        self.assertIn("scheduleNarrowDetailReveal", app)
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
        self.assertNotIn("min-width: 320px", css)
        self.assertIn("touch-action: pan-x pan-y", css)
        self.assertIn("height: var(--call-inspector-height", css)
        self.assertIn("call-function-meta", app)
        self.assertIn("call-function-meta", css)
        self.assertIn("note.context", app)
        self.assertIn("Outside conditional context", app)
        self.assertIn("rightCharacters", app)
        self.assertIn("kindWidth", app)
        self.assertIn('data-view="dictionary"', html)
        self.assertIn("wake_bootset", html)
        self.assertNotIn("wake_engine", html)
        self.assertIn('id="dictionarySearch"', html)
        self.assertIn("renderDictionaryCatalog", app)
        self.assertIn("renderDictionaryCatalog({ revealDetail: true })", app)
        self.assertIn("dictionary-card", css)
        self.assertNotIn('id="currentBranch"', html)
        self.assertNotIn("branch-chip", app)


if __name__ == "__main__":
    unittest.main()
