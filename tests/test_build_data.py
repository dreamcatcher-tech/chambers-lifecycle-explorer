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
                "boot-crash-repair",
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
        self.assertEqual((16, 198, 59, 137, 61, 57), (
            chambers["sequences"], chambers["calls"], chambers["functions"],
            chambers["i3Calls"], chambers["hostCalls"], chambers["dictionaryTerms"],
        ))
        cardflow = self.documents["cardflow"]["stats"]
        self.assertEqual((9, 66, 33, 66, 0, 30), (
            cardflow["sequences"], cardflow["calls"], cardflow["functions"],
            cardflow["i3Calls"], cardflow["hostCalls"], cardflow["dictionaryTerms"],
        ))
        self.assertEqual(87, self.payload["stats"]["dictionaryTerms"])

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

    def test_host_boundary_is_explicit_and_chambers_only(self) -> None:
        chambers_host = {
            function["id"]
            for function in self.documents["chambers"]["functions"]
            if function["kind"] == "host"
        }
        self.assertEqual(
            {
                "install_boot_seed", "wake_bootset", "repair_boot_member", "deliver_final_reply",
                "bootset_selector_seed", "bootset_selector_read", "bootset_selector_fallback",
                "persistence_volume_attach", "persistence_volume_release", "containerd_import",
                "containerd_resolve", "containerd_task_start", "containerd_task_stop",
            },
            chambers_host,
        )
        self.assertTrue(all(function["kind"] == "i3" for function in self.documents["cardflow"]["functions"]))

    def test_chambers_display_starts_with_genesis_bootstrap_reboot_repair_then_ordinary_activation(self) -> None:
        sequences = self.documents["chambers"]["sequences"]
        self.assertEqual(
            [
                ("core-installation", "First boot installation"),
                ("host-activation", "Selected Boot set cold start"),
                ("core-bootstrap", "Boot control bootstrap"),
                ("core-reboot", "Reboot selected Boot set"),
                ("boot-crash-repair", "Same-selection crash repair"),
                ("activation-kernel", "Ordinary activation"),
            ],
            [(sequence["id"], sequence["shortTitle"]) for sequence in sequences[:6]],
        )
        self.assertEqual(list(range(1, len(sequences) + 1)), [sequence["ordinal"] for sequence in sequences])

        by_id = {sequence["id"]: sequence for sequence in sequences}
        installation_calls = [call["function"] for call in by_id["core-installation"]["calls"]]
        host_calls = [call["function"] for call in by_id["host-activation"]["calls"]]
        core_calls = [call["function"] for call in by_id["core-bootstrap"]["calls"]]
        reboot_calls = [call["function"] for call in by_id["core-reboot"]["calls"]]
        ordinary_calls = [call["function"] for call in by_id["activation-kernel"]["calls"]]
        self.assertIn("containerd_import", installation_calls)
        self.assertIn("bootset_selector_seed", installation_calls)
        self.assertNotIn("containerd_tag_update", installation_calls)
        self.assertEqual(1, host_calls.count("bootset_selector_read"))
        self.assertEqual(4, host_calls.count("containerd_task_start"))
        self.assertIn("persistence_volume_attach", host_calls)
        self.assertNotIn("persistence::realization::read", host_calls)
        self.assertEqual(2, core_calls.count("routing::authenticate"))
        self.assertEqual(2, core_calls.count("routing::authorize_registration"))
        self.assertIn("persistence::routing::read", core_calls)
        self.assertIn("routing::reconcile", core_calls)
        self.assertEqual(1, reboot_calls.count("bootset_selector_read"))
        self.assertNotIn("persistence::realization::read", reboot_calls)
        self.assertIn("persistence::realization::read", ordinary_calls)
        self.assertIn("chamber::activate", ordinary_calls)
        self.assertIn("wake_bootset", host_calls)
        self.assertNotIn("engine::identity::attest", host_calls)

        cold_starts = [call for call in by_id["host-activation"]["calls"] if call["function"] == "containerd_task_start"]
        branches = {context["branch"] for call in cold_starts for context in call["context"]}
        self.assertIn("Selected and authorized-fallback closures are exact and retained", branches)
        notes = " ".join(note["text"] for call in cold_starts for note in call["notes"])
        for marker in ("Fresh Engine", "Fresh Persistence", "Fresh Gateway", "Fresh Supervisor"):
            self.assertIn(marker, notes)

    def test_host_agent_and_containerd_projection_preserve_authority_order(self) -> None:
        chambers = self.documents["chambers"]
        boot_order = ["Engine", "Persistence", "Gateway", "Supervisor"]
        for sequence in chambers["sequences"]:
            participant_ids = [participant["id"] for participant in sequence["participants"]]
            if "HostAgent" in participant_ids:
                self.assertEqual("HostAgent", participant_ids[0], sequence["id"])
            present = [item for item in boot_order if item in participant_ids]
            self.assertEqual(sorted(participant_ids.index(item) for item in present), [participant_ids.index(item) for item in present])
            for call in sequence["calls"]:
                if call["to"] == "containerd":
                    self.assertEqual("HostAgent", call["from"], sequence["id"])
                    self.assertTrue(call["function"].startswith("containerd_"), sequence["id"])
                self.assertNotEqual("containerd", call["from"], sequence["id"])
            self.assertNotIn("Runtime", participant_ids)
            self.assertNotIn("Materializer", participant_ids)
            self.assertNotIn("procman", participant_ids)
            self.assertNotIn("Router", participant_ids)

        host_activation = next(sequence for sequence in chambers["sequences"] if sequence["id"] == "host-activation")
        roles = {participant["id"]: participant["role"] for participant in host_activation["participants"]}
        self.assertEqual("host", roles["HostAgent"])
        self.assertEqual("host", roles["containerd"])
        self.assertEqual("resource", roles["BootControl"])
        self.assertEqual("resource", roles["Volume"])
        self.assertEqual("resource", roles["Persistence"])
        self.assertEqual("control", roles["Gateway"])

        functions = {function["id"]: function for function in chambers["functions"]}
        self.assertEqual("Host Agent", functions["chamber::activate"]["owner"])
        self.assertEqual("Host Agent", functions["bootset::restart"]["owner"])
        self.assertEqual("Persistence", functions["persistence::bootset::commit"]["owner"])
        self.assertEqual("boot-control slice, containerd, and boot members", functions["containerd_task_start"]["owner"])
        self.assertEqual("Gateway", functions["routing::reconcile"]["owner"])

    def test_protected_boot_and_reconstructable_runtime_semantics_survive_projection(self) -> None:
        chambers = self.documents["chambers"]
        snapshot = (ROOT / "source" / chambers["source"]["snapshotPath"]).read_text(encoding="utf-8")
        flat = snapshot.replace("\n", " ")
        self.assertNotIn("Filesystem Service", snapshot)
        self.assertNotIn("filesystem::", snapshot)
        self.assertIn("containerd protected boot namespace = immutable Boot-set manifests", snapshot)
        self.assertIn("containerd ordinary runtime namespace = reconstructable", snapshot)
        self.assertIn("containerd state directory = volatile runtime state", snapshot)
        self.assertIn("durable Ark volume -> boot-control slice + Persistence data", snapshot)
        self.assertIn("Persistence is the only Chamber with the authoritative RW host-backed volume", flat)
        self.assertIn("Host Agent normally reads only the `boot-control` slice at a cold boundary", flat)

        roles: dict[str, set[str]] = {}
        for sequence in chambers["sequences"]:
            for participant in sequence["participants"]:
                roles.setdefault(participant["id"], set()).add(participant["role"])
        self.assertEqual({"resource"}, roles["Persistence"])
        self.assertEqual({"resource"}, roles["BootControl"])
        self.assertEqual({"resource"}, roles["Volume"])
        self.assertEqual({"control"}, roles["Gateway"])

        calls = [call for sequence in chambers["sequences"] for call in sequence["calls"]]
        self.assertFalse(any(call["from"] == "containerd" for call in calls))
        self.assertFalse(any({call["from"], call["to"]} == {"containerd", "Persistence"} for call in calls))
        build = next(sequence for sequence in chambers["sequences"] if sequence["id"] == "artifact-build")
        self.assertNotIn("containerd", {participant["id"] for participant in build["participants"]})
        self.assertIn("persistence::build::record", [call["function"] for call in build["calls"]])

    def test_engine_first_bootset_and_whole_stack_replacement_survive_projection(self) -> None:
        chambers = self.documents["chambers"]
        snapshot = (ROOT / "source" / chambers["source"]["snapshotPath"]).read_text(encoding="utf-8")
        flat = snapshot.replace("\n", " ")
        self.assertIn("boot-control/selected.json", snapshot)
        self.assertIn("Engine, Persistence, Gateway, Supervisor", snapshot)
        self.assertIn("Gateway combines Router, RBAC/authorization, bounded volatile buffering", flat)
        self.assertIn("Any selected Boot-set member change", snapshot)
        self.assertIn("one-attempt last-known-good fallback", snapshot)
        self.assertIn("Builder remains outside every boot Chamber", snapshot)
        self.assertNotIn("dreamcatcher/bootset:current", snapshot)
        self.assertNotIn("routing::claim", snapshot)

        sequences = {sequence["id"]: sequence for sequence in chambers["sequences"]}
        reboot_functions = [call["function"] for call in sequences["core-reboot"]["calls"]]
        self.assertEqual(4, reboot_functions.count("containerd_task_start"))
        self.assertEqual(1, reboot_functions.count("bootset_selector_read"))
        self.assertNotIn("containerd_import", reboot_functions)

        selection_functions = [call["function"] for call in sequences["selection-rollback"]["calls"]]
        self.assertLess(selection_functions.index("bootset::stage"), selection_functions.index("persistence::bootset::commit"))
        self.assertLess(selection_functions.index("persistence::bootset::commit"), selection_functions.index("bootset::restart"))
        self.assertNotIn("containerd_tag_update", selection_functions)

        replacement = [call["function"] for call in sequences["core-cutover"]["calls"]]
        self.assertEqual(4, replacement.count("containerd_task_start"))
        self.assertEqual(5, replacement.count("containerd_task_stop"))
        for function in ("bootset_selector_read", "bootset_selector_fallback", "persistence_volume_attach", "persistence_volume_release"):
            self.assertIn(function, replacement)

        ordinary = [call["function"] for call in sequences["ordinary-routed-cutover"]["calls"]]
        for function in ("routing::fence", "persistence::selection::commit", "routing::install", "routing::reopen"):
            self.assertIn(function, ordinary)
        self.assertNotIn("persistence::bootset::commit", ordinary)

    def test_replacement_fallback_and_crash_context_survive_projection(self) -> None:
        chambers = self.documents["chambers"]
        sequences = {sequence["id"]: sequence for sequence in chambers["sequences"]}
        replacement = sequences["core-cutover"]
        participants = {participant["id"]: participant["role"] for participant in replacement["participants"]}
        self.assertEqual("resource", participants["BootControl"])
        self.assertEqual("resource", participants["Volume"])
        self.assertEqual("resource", participants["Persistence"])
        self.assertEqual("control", participants["Gateway"])

        branch_of = lambda call: {context["branch"] for context in call["context"]}
        fallback = next(call for call in replacement["calls"] if call["function"] == "bootset_selector_fallback")
        self.assertIn("Successor does not become ready", branch_of(fallback))
        self.assertIn("Failure precedes admission/effects and exact fallback is eligible", branch_of(fallback))
        self.assertTrue(any("one-attempt permit" in note["text"] for note in fallback["notes"]))

        ordinary = sequences["ordinary-routed-cutover"]
        success_install = next(call for call in ordinary["calls"] if call["function"] == "routing::install")
        self.assertIn("Successor selection and exact readiness agree", branch_of(success_install))
        failed_stop = next(
            call for call in ordinary["calls"]
            if call["function"] == "chamber::stop"
            and "Ordinary compare-and-swap or successor readiness fails" in branch_of(call)
        )
        self.assertTrue(any("reap failed candidate" in note["text"] for note in failed_stop["notes"]))

        repair = sequences["boot-crash-repair"]
        repair_branches = {
            branch for call in repair["calls"] for branch in branch_of(call)
            if branch.startswith("Exact selected") or branch.startswith("Engine crashed")
        }
        self.assertEqual(
            {
                "Exact selected Supervisor crashed",
                "Exact selected Persistence crashed",
                "Exact selected Gateway crashed",
                "Engine crashed, identity or volume fence is uncertain, or bounded repair failed",
            },
            repair_branches,
        )
        self.assertNotIn("bootset_selector_read", [call["function"] for call in repair["calls"]])

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
        self.assertIn("not an alias for Realization", chambers["covenant-lock"]["definition"])
        self.assertIn("Covenant lock plus one normalized launch specification", chambers["realization"]["definition"])
        self.assertIn("boot-set-selection", chambers["boot-set"]["related"])
        self.assertIn("bootstrap-engine-covenant", chambers["boot-set"]["related"])
        self.assertIn("gateway-covenant", chambers["boot-set"]["related"])
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
