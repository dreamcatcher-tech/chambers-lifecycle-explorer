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
                "boot-crash-repair",
                "scope-bound-child-core",
                "candidate-formation",
                "fenced-development",
                "artifact-build",
                "attested-builds",
                "candidate-verification",
                "selection-rollback",
                "prepared-execution",
                "ordinary-routed-cutover",
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
        self.assertEqual((16, 141, 52, 130, 11, 52), (
            chambers["sequences"], chambers["calls"], chambers["functions"],
            chambers["i3Calls"], chambers["hostCalls"], chambers["dictionaryTerms"],
        ))
        cardflow = self.documents["cardflow"]["stats"]
        self.assertEqual((9, 66, 33, 66, 0, 30), (
            cardflow["sequences"], cardflow["calls"], cardflow["functions"],
            cardflow["i3Calls"], cardflow["hostCalls"], cardflow["dictionaryTerms"],
        ))
        self.assertEqual(82, self.payload["stats"]["dictionaryTerms"])

    def test_prepared_image_and_execution_profile_projection_survives(self) -> None:
        chambers = self.documents["chambers"]
        by_id = {sequence["id"]: sequence for sequence in chambers["sequences"]}
        preparation = by_id["candidate-verification"]
        execution = by_id["prepared-execution"]

        preparation_calls = [call["function"] for call in preparation["calls"]]
        self.assertLess(preparation_calls.index("chamber::stop"), preparation_calls.index("artifact::retain"))
        self.assertLess(preparation_calls.index("artifact::retain"), preparation_calls.index("persistence::prepared::record"))
        preparation_notes = " ".join(note["text"] for call in preparation["calls"] for note in call["notes"])
        self.assertIn("never commit or reuse its writable snapshot", preparation_notes)

        execution_calls = [call["function"] for call in execution["calls"]]
        for function in ("chamber::job::run", "job::invoke", "chamber::stop", "routing::install", "routing::reopen"):
            self.assertIn(function, execution_calls)
        terms = {entry["term"] for entry in chambers["dictionary"]}
        self.assertTrue({"Prepared Realization", "Execution profile", "Dynamic job", "Resident service"} <= terms)

    def test_host_boundary_is_intent_level_and_chambers_only(self) -> None:
        chambers_host = {
            function["id"]
            for function in self.documents["chambers"]["functions"]
            if function["kind"] == "host"
        }
        self.assertEqual(
            {"install_core_seed", "wake_ark_core", "recover_ark_tree", "start_ark_core", "deliver_final_reply"},
            chambers_host,
        )
        self.assertTrue(all(function["kind"] == "i3" for function in self.documents["cardflow"]["functions"]))

    def test_chambers_display_starts_with_install_bootstrap_recovery_child_then_ordinary(self) -> None:
        sequences = self.documents["chambers"]["sequences"]
        self.assertEqual(
            [
                ("core-installation", "First Ark Core installation"),
                ("host-activation", "Selected Ark Core cold start"),
                ("core-bootstrap", "Ark Core bootstrap"),
                ("boot-crash-repair", "Whole-appliance recovery"),
                ("scope-bound-child-core", "Child Ark Core scope"),
                ("activation-kernel", "Ordinary activation"),
            ],
            [(sequence["id"], sequence["shortTitle"]) for sequence in sequences[:6]],
        )
        self.assertEqual(list(range(1, len(sequences) + 1)), [sequence["ordinal"] for sequence in sequences])

        by_id = {sequence["id"]: sequence for sequence in sequences}
        installation_calls = [call["function"] for call in by_id["core-installation"]["calls"]]
        host_calls = [call["function"] for call in by_id["host-activation"]["calls"]]
        core_calls = [call["function"] for call in by_id["core-bootstrap"]["calls"]]
        recovery_calls = [call["function"] for call in by_id["boot-crash-repair"]["calls"]]
        child_calls = [call["function"] for call in by_id["scope-bound-child-core"]["calls"]]
        ordinary_calls = [call["function"] for call in by_id["activation-kernel"]["calls"]]

        self.assertEqual(["install_core_seed", "start_ark_core"], installation_calls[:2])
        self.assertEqual(1, host_calls.count("wake_ark_core"))
        self.assertGreaterEqual(host_calls.count("start_ark_core"), 1)
        self.assertEqual(2, core_calls.count("routing::authenticate"))
        self.assertEqual(2, core_calls.count("routing::authorize_registration"))
        self.assertIn("persistence::routing::read", core_calls)
        self.assertIn("routing::reconcile", core_calls)
        self.assertIn("recover_ark_tree", recovery_calls)
        self.assertIn("start_ark_core", recovery_calls)
        self.assertIn("ark::core::activate", child_calls)
        self.assertIn("chamber::activate", child_calls)
        self.assertIn("persistence::realization::read", ordinary_calls)
        self.assertIn("chamber::activate", ordinary_calls)
        self.assertFalse(any(call.startswith(("containerd_", "persistence_volume_", "bootset_")) for call in host_calls))

    def test_host_agent_projection_preserves_scope_authority_and_hides_runtime_chatter(self) -> None:
        chambers = self.documents["chambers"]
        worker_order = ["Engine", "Persistence", "Gateway", "Supervisor"]
        forbidden_lanes = {"containerd", "BootControl", "Volume", "Runtime", "Materializer", "Router"}
        for sequence in chambers["sequences"]:
            participant_ids = [participant["id"] for participant in sequence["participants"]]
            if "HostAgent" in participant_ids:
                self.assertEqual("HostAgent", participant_ids[0], sequence["id"])
            self.assertFalse(forbidden_lanes.intersection(participant_ids), sequence["id"])
            present = [item for item in worker_order if item in participant_ids]
            self.assertEqual(sorted(participant_ids.index(item) for item in present), [participant_ids.index(item) for item in present])
            for call in sequence["calls"]:
                self.assertFalse(call["function"].startswith(("containerd_", "persistence_volume_", "bootset_")))

        host_activation = next(sequence for sequence in chambers["sequences"] if sequence["id"] == "host-activation")
        roles = {participant["id"]: participant["role"] for participant in host_activation["participants"]}
        self.assertEqual("host", roles["HostAgent"])
        self.assertEqual("engine", roles["Core"])
        self.assertEqual("resource", roles["Persistence"])
        self.assertEqual("control", roles["Gateway"])

        functions = {function["id"]: function for function in chambers["functions"]}
        self.assertEqual("Host Agent", functions["chamber::activate"]["owner"])
        self.assertEqual("Host Agent", functions["ark::core::restart"]["owner"])
        self.assertEqual("Persistence", functions["persistence::core::commit"]["owner"])
        self.assertEqual("Gateway", functions["routing::reconcile"]["owner"])
        self.assertEqual("External conventional call (not I3)", functions["start_ark_core"]["path"])

    def test_ark_core_scope_and_private_network_semantics_survive_projection(self) -> None:
        chambers = self.documents["chambers"]
        snapshot = (ROOT / "source" / chambers["source"]["snapshotPath"]).read_text(encoding="utf-8")
        flat = snapshot.replace("\n", " ")
        for marker in (
            "one exact OCI image, one gVisor task, one s6 PID 1",
            "any required Core process exit or semantic-readiness loss -> complete Core-task exit -> complete scope recovery",
            "s6 as container PID 1, with one-shot bootstrap seeding accepted runtime bytes into private `/run/iii` tmpfs",
            "127.0.0.1:49133",
            "Ark-private scope listener at port `49134`",
            "There is no host port mapping, host-network mode, donated Unix socket, or TCP fallback",
            "explicit forwarding-deny fence separates sibling CIDRs",
            "ordinary descendants receive no Ark-volume contents",
            "22/22 independently verified checks",
            "s6 whole-appliance fatality, production containerd/CNI-plugin, and storage-driver integration require their own acceptance evidence",
            "no member-local restart path",
            "Builder as an ordinary separate sandbox",
        ):
            self.assertIn(marker, flat)
        for retired in ("Boot set", "Boot-set", "bootset::", "repair_boot_member"):
            self.assertNotIn(retired, snapshot)

        roles: dict[str, set[str]] = {}
        for sequence in chambers["sequences"]:
            for participant in sequence["participants"]:
                roles.setdefault(participant["id"], set()).add(participant["role"])
        self.assertEqual({"resource"}, roles["Persistence"])
        self.assertEqual({"control"}, roles["Gateway"])
        self.assertEqual({"engine"}, roles["Engine"])

        build = next(sequence for sequence in chambers["sequences"] if sequence["id"] == "artifact-build")
        self.assertIn("persistence::build::record", [call["function"] for call in build["calls"]])

    def test_core_selection_replacement_and_ordinary_handover_remain_distinct(self) -> None:
        chambers = self.documents["chambers"]
        sequences = {sequence["id"]: sequence for sequence in chambers["sequences"]}
        selection = [call["function"] for call in sequences["selection-rollback"]["calls"]]
        self.assertLess(selection.index("ark::core::stage"), selection.index("persistence::core::commit"))
        self.assertLess(selection.index("persistence::core::commit"), selection.index("ark::core::restart"))

        replacement = [call["function"] for call in sequences["core-cutover"]["calls"]]
        for function in ("ark::core::stage", "ark::core::inspect", "persistence::core::commit", "ark::core::restart", "start_ark_core"):
            self.assertIn(function, replacement)
        self.assertNotIn("routing::install", replacement)
        self.assertNotIn("routing::reopen", replacement)

        ordinary = [call["function"] for call in sequences["ordinary-routed-cutover"]["calls"]]
        for function in ("routing::fence", "persistence::selection::commit", "routing::install", "routing::reopen"):
            self.assertIn(function, ordinary)
        self.assertNotIn("persistence::core::commit", ordinary)
        self.assertNotIn("ark::core::restart", ordinary)

    def test_fallback_whole_recovery_and_child_scope_context_survive_projection(self) -> None:
        chambers = self.documents["chambers"]
        sequences = {sequence["id"]: sequence for sequence in chambers["sequences"]}
        branch_of = lambda call: {context["branch"] for context in call["context"]}

        replacement = sequences["core-cutover"]
        fallback_start = next(
            call for call in reversed(replacement["calls"])
            if call["function"] == "start_ark_core" and "Exact fallback remains eligible" in branch_of(call)
        )
        self.assertIn("Successor does not become ready", branch_of(fallback_start))
        self.assertTrue(any("pre-authorized recovery selector once" in note["text"] for note in fallback_start["notes"]))

        ordinary = sequences["ordinary-routed-cutover"]
        success_install = next(call for call in ordinary["calls"] if call["function"] == "routing::install")
        self.assertIn("Successor selection and exact readiness agree", branch_of(success_install))
        failed_stop = next(
            call for call in ordinary["calls"]
            if call["function"] == "chamber::stop"
            and "Ordinary compare-and-swap or successor readiness fails" in branch_of(call)
        )
        self.assertTrue(any("reap failed candidate" in note["text"] for note in failed_stop["notes"]))

        recovery = sequences["boot-crash-repair"]
        recovery_functions = [call["function"] for call in recovery["calls"]]
        self.assertIn("recover_ark_tree", recovery_functions)
        self.assertIn("start_ark_core", recovery_functions)
        self.assertNotIn("persistence::core::commit", recovery_functions)
        recovery_notes = " ".join(note["text"] for call in recovery["calls"] for note in call["notes"])
        self.assertIn("Never restart an internal worker", recovery_notes)
        self.assertIn("s6 stops the whole tree and exits PID 1 with no member-local restart", recovery_notes)
        self.assertIn("new task ID from the unchanged selected Core and volume", recovery_notes)

        child = sequences["scope-bound-child-core"]
        child_notes = " ".join(note["text"] for call in child["calls"] for note in call["notes"])
        self.assertIn("new child scope, private network, test volume, selector", child_notes)
        self.assertIn("authenticated child session supplies scope", child_notes)
        self.assertIn("payload routing fields are rejected", child_notes)
        self.assertIn("deny forwarding to parent and sibling scope networks", child_notes)
        self.assertIn("cannot see parent siblings, another root Ark", child_notes)
        self.assertIn("denied recursive activation, cross-scope routes, runtime handles", child_notes)

        forbidden = {"routing::reconcile", "routing::fence", "routing::install", "routing::reopen"}
        all_calls = [call for sequence in chambers["sequences"] for call in sequence["calls"]]
        self.assertFalse(any(call["from"] == "HostAgent" and call["function"] in forbidden for call in all_calls))

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
        self.assertIn("not launch authority", chambers["covenant-lock"]["definition"])
        self.assertIn("one exact Covenant lock plus one normalized launch specification", chambers["realization"]["definition"])
        self.assertIn("ark-core-selection", chambers["ark-core-appliance"]["related"])
        self.assertIn("ark-scope", chambers["ark-core-appliance"]["related"])
        self.assertIn("engine", chambers["ark-core-appliance"]["related"])
        self.assertIn("gateway", chambers["ark-core-appliance"]["related"])
        self.assertIn("persistence", chambers["ark-core-appliance"]["related"])
        self.assertIn("supervisor", chambers["ark-core-appliance"]["related"])

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
        self.assertIn("wake_ark_core", html)
        self.assertNotIn("wake_engine", html)
        self.assertIn('id="dictionarySearch"', html)
        self.assertIn("renderDictionaryCatalog", app)
        self.assertIn("renderDictionaryCatalog({ revealDetail: true })", app)
        self.assertIn("dictionary-card", css)
        self.assertNotIn('id="currentBranch"', html)
        self.assertNotIn("branch-chip", app)


if __name__ == "__main__":
    unittest.main()
