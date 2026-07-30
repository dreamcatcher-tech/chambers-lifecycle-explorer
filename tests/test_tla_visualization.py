from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTION_PATH = ROOT / "source" / "tla-model-projection.json"
ANNOTATIONS_PATH = ROOT / "scripts" / "tla_model_annotations.json"


class TlaVisualizationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.projection = json.loads(PROJECTION_PATH.read_text(encoding="utf-8"))
        cls.annotations = json.loads(ANNOTATIONS_PATH.read_text(encoding="utf-8"))
        cls.models = {model["id"]: model for model in cls.projection["models"]}

    def test_projection_is_exactly_bound_to_checked_temporal_commit(self) -> None:
        self.assertEqual(self.projection["schema"], "dreamcatcher.chambers-tla-model-projection/v2")
        source = self.projection["source"]
        self.assertEqual(source["repository"], "dreamcatcher-tech/chambers-temporal-model")
        self.assertEqual(source["visibility"], "private")
        self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
        self.assertRegex(source["evidenceSha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            source["authority"]["repository"], "dreamcatcher-tech/fundamentals"
        )
        self.assertEqual(
            source["architectureSynthesis"]["acceptedPartition"], "E+A+R+P+S"
        )

    def test_complete_dot_aggregates_cover_every_checked_state_and_transition(self) -> None:
        for model in self.models.values():
            state_space = model["stateSpace"]
            self.assertEqual(state_space["kind"], "complete_tlc_dot_aggregation")
            self.assertEqual(
                sum(node["concreteStates"] for node in state_space["nodes"]),
                model["check"]["distinctStates"],
                model["id"],
            )
            self.assertEqual(
                sum(row["concreteTransitions"] for row in state_space["transitions"]),
                model["check"]["generatedStates"] - 1,
                model["id"],
            )
            self.assertRegex(state_space["aggregateSha256"], r"^[0-9a-f]{64}$")

    def test_ark_core_mode_lens_has_all_seven_modes(self) -> None:
        model = self.models["ark_core_appliance"]
        nodes = {node["id"]: node["concreteStates"] for node in model["stateSpace"]["nodes"]}
        self.assertEqual(
            set(nodes),
            {"Off", "Starting", "Ready", "Fenced", "Crashed", "Recovery", "Terminal"},
        )
        self.assertEqual(sum(nodes.values()), 502)
        action = next(item for item in model["actions"] if item["id"] == "MemberLocalRespawn")
        self.assertFalse(action["reachableInPrincipal"])
        self.assertEqual(action["concreteTransitionCount"], 0)

    def test_multi_ark_lens_contains_all_phase_tuples(self) -> None:
        model = self.models["multi_ark"]
        nodes = model["stateSpace"]["nodes"]
        self.assertEqual(len(nodes), 43)
        expected = {"Off", "Starting", "Ready", "Crashed", "Reaped"}
        for node in nodes:
            self.assertEqual(set(node["values"]), {"Root", "Child", "Grandchild"})
            self.assertTrue(set(node["values"].values()) <= expected)
        self.assertEqual(sum(node["concreteStates"] for node in nodes), 284)

    def test_host_cutover_lens_is_the_exact_eleven_state_chain(self) -> None:
        model = self.models["host_cutover"]
        self.assertEqual(model["check"]["distinctStates"], 11)
        self.assertEqual(model["stateSpace"]["concreteStates"], 11)
        self.assertEqual(model["stateSpace"]["concreteTransitions"], 10)
        self.assertEqual(
            [edge["actions"][0] for edge in model["curated"]["edges"]],
            [scenario_action for scenario_action in model["scenarios"][0]["steps"]],
        )

    def test_curated_names_are_all_resolved_in_generated_operator_registry(self) -> None:
        for model_id, annotation in self.annotations["models"].items():
            generated = self.models[model_id]
            actions = {action["id"] for action in generated["actions"]}
            self.assertEqual(actions, set(annotation["actions"]), model_id)
            for scenario in generated["scenarios"]:
                self.assertTrue(set(scenario["steps"]) <= actions, scenario["id"])
            for edge in generated["curated"]["edges"]:
                self.assertTrue(set(edge.get("actions", [])) <= actions)

    def test_all_seven_weakened_controls_have_real_counterexample_receipts(self) -> None:
        controls = self.projection["negativeControls"]
        self.assertEqual(len(controls), 7)
        self.assertEqual(
            {control["id"] for control in controls},
            set(self.annotations["negative_controls"]),
        )
        for control in controls:
            self.assertEqual(control["status"], "expected_counterexample")
            self.assertGreater(control["traceDepth"], 0)
            self.assertGreater(control["distinctStates"], 0)

    def test_complete_dot_operator_labels_are_annotated_without_observer_state(self) -> None:
        for model in self.models.values():
            action_ids = {action["id"] for action in model["actions"]}
            operators = {
                transition["operator"]
                for transition in model["stateSpace"]["transitions"]
            }
            self.assertTrue(operators <= action_ids, model["id"])
        self.assertNotIn("lastAction", self.models["multi_ark"]["variables"])

    def test_projection_does_not_publish_raw_private_tla_or_dot_states(self) -> None:
        text = PROJECTION_PATH.read_text(encoding="utf-8")
        for forbidden in (
            "UNCHANGED <<",
            "VARIABLES\\n",
            "/\\\\ roleReady =",
            "productionWriters = {",
            "ordinaryAuthorityEdges = {",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("excludes raw private TLA+ source", text)
        self.assertIn("complete_tlc_dot_aggregation", text)

    def test_generated_browser_bundle_is_exact(self) -> None:
        bundle = (ROOT / "site" / "tla" / "model-data.js").read_text(encoding="utf-8")
        prefix = "// Generated from source/tla-model-projection.json. Do not edit.\nwindow.CHAMBERS_TLA_MODEL = "
        self.assertTrue(bundle.startswith(prefix))
        self.assertTrue(bundle.endswith(";\n"))
        payload = json.loads(bundle[len(prefix) : -2])
        self.assertEqual(payload, self.projection)

    def test_lifecycle_atlas_links_to_a_self_contained_tla_page(self) -> None:
        root_html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
        root_css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")
        page = (ROOT / "site" / "tla" / "index.html").read_text(encoding="utf-8")
        app = (ROOT / "site" / "tla" / "app.js").read_text(encoding="utf-8")
        self.assertIn('href="./tla/"', root_html)
        self.assertIn("TLA+ Model", root_html)
        self.assertIn("@media (max-width: 360px)", root_css)
        self.assertIn(".tla-model-link span { display: none; }", root_css)
        self.assertIn('src="./model-data.js"', page)
        self.assertIn('src="./app.js"', page)
        self.assertNotRegex(page, r'<(?:script|link)[^>]+(?:src|href)="https?://')
        self.assertNotIn("innerHTML", app)
        self.assertIn('toggleAttribute("hidden", hidden)', app)
        self.assertNotIn("modelSvg.hidden", app)
        for marker in ("renderExplainGraph", "renderTupleMatrix", "renderProperties"):
            self.assertIn(marker, app)


if __name__ == "__main__":
    unittest.main()
