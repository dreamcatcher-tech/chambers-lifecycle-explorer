# TLA+ model visualization refresh runbook

This runbook maintains the TLA+ Model Explorer published at:

<https://dreamcatcher-tech.github.io/chambers-lifecycle-explorer/tla/>

The temporal source repository is private. The GitHub Pages repository is public. Treat synchronization as an explicit disclosure boundary, not as a generic copy operation.

## What the three views mean

The page deliberately separates three kinds of information:

1. **Explain** — a curated, human-readable state/action or scope-topology map. Layout, descriptions, and walkthrough paths live in `scripts/tla_model_annotations.json`. The synchronization script fails if an annotated action or property name no longer resolves in the exact TLA+ module. This view explains the model but is **not** claimed to be a complete semantic derivation.
2. **TLC state space** — an automatically generated aggregation of complete Graphviz DOT state graphs emitted reproducibly by `tlc2.TLC -seed 1 -dump dot,actionlabels,colorize`. Every parsed concrete state and transition must be accounted for, and its count must agree with the checked evidence receipt. Raw private state labels and raw DOT files are not published.
3. **Properties** — configured safety/liveness operators and the real TLC receipts for twelve deliberately weakened controls in the published subset. A passing bounded check is model evidence, not implementation conformance.

This distinction is a publication contract. Do not merge the curated and generated labels or describe the Explain view as “generated from all TLA+ semantics.”

## Why not publish the ordinary TLC graph directly?

TLC and the TLA+ Toolbox can generate a Graphviz state graph. The official TLA+ documentation warns that this is useful only for small state spaces because fully expanded DOT rendering becomes unreadable or times out as models grow. The current checked public subset has 833 distinct states and 2,646 transitions across four models.

The explorer therefore keeps the exact complete graph as a private build intermediate and publishes bounded aggregates:

- `ArkCoreAppliance`: 502 states grouped by the scalar `mode` variable;
- `MultiArk`: 284 states grouped into 43 reachable `Root / Child / Grandchild` phase tuples and shown as a matrix;
- `HostCutover`: 11 exact states grouped into 9 incumbent/candidate phase tuples, with the Explain view retaining the 11-step action chain.
- `BaselineComposition`: 36 checked states grouped into 15 exact lifecycle phases from mutable workspace through one-way successor cutover.

Compact authority models do not retain an observer-only `lastAction` variable. The projection therefore takes concrete transition labels directly from TLC's `actionlabels` DOT edges, requires every emitted operator to have a source-resolving annotation, and still accounts for every checked state and transition. Because TLC DOT bytes contain opaque JVM graph identifiers that are not byte-stable across equivalent runs, projection schema v3 publishes `aggregateSha256`: a canonical SHA-256 over the complete parsed aggregate nodes and transitions, rather than a misleading raw-DOT byte hash. The formal release contains eleven kernels; this public page deliberately projects four and labels that coverage boundary explicitly.

References:

- <https://docs.tlapl.us/using:generating_state_graphs>
- <https://tla.msr-inria.inria.fr/tlatoolbox/doc/model/tlc-options-page.html>

## Data flow and disclosure boundary

```text
private chambers-temporal-model @ exact ratified release tag/commit
  ├─ model/*.tla + principal *.cfg
  ├─ release/specification.json + release/manifest.json + CHANGELOG.md
  ├─ evidence/model-check-summary.json
  └─ source/provenance.json (lineage only, never authority)
          │
          │ fresh official Java/TLC run + complete DOT parse
          ▼
public source/tla-model-projection.json
  ├─ exact commit, file hashes, source line anchors
  ├─ action/variable/property names
  ├─ complete aggregate state + transition counts
  ├─ passing model-check receipt
  └─ expected-counterexample receipts
          │
          ▼
site/tla/model-data.js → site/tla/index.html + app.js + styles.css
```

Never publish:

- raw private `.tla` or `.cfg` bytes;
- raw DOT files or concrete state labels;
- raw TLC logs from the private model repository;
- credentials or local filesystem paths.

The projection may publish exact names, hashes, line anchors, aggregate values, and already approved architecture descriptions. Any broader disclosure requires separate review.

## Refresh from a newer temporal-model commit

### 1. Synchronize and verify the private source

```bash
git -C ../chambers-temporal-model fetch --all --prune
git -C ../chambers-temporal-model pull --ff-only
git -C ../chambers-temporal-model status --short --branch
```

The source checkout must be clean and `HEAD` must equal its upstream. Its `release/specification.json` must declare a ratified release whose exact Git tag resolves to `HEAD`, and the manifest must bind the committed evidence. The generator refuses a dirty, unpublished, untagged, or mismatched source by default.

Run the temporal repository's own evidence/check process first. Its official Java-based SANY/TLC checks remain the authority for the receipt; this site does not replace them.

### 2. Regenerate the public-safe projection

```bash
JAVA=/path/to/java \
TLA_JAR=/path/to/tla2tools-1.7.4.jar \
TEMPORAL_MODEL=../chambers-temporal-model \
make sync-tla
```

The synchronization script:

1. verifies source cleanliness and upstream equality;
2. verifies that the ratified release tag resolves to the exact source commit and that its manifest binds the evidence;
3. verifies the TLA+ tools jar SHA-256 against committed evidence;
4. verifies current module/config hashes against the evidence receipt;
5. runs each published principal configuration through official `tlc2.TLC` with deterministic DOT seed `1`;
6. parses the complete DOT graph without publishing it;
7. cross-checks DOT state and transition counts against committed evidence;
8. validates every curated action and invariant name against the live module;
9. writes `source/tla-model-projection.json` and then `site/tla/model-data.js`.

### 3. Review the disclosure diff

```bash
git diff -- source/tla-model-projection.json site/tla/model-data.js \
  scripts/tla_model_annotations.json
git diff --check
```

Confirm that only expected names, descriptions, aggregates, hashes, and receipts changed. Search specifically for raw assignment/state text if model parsing was modified.

### 4. Validate locally

```bash
make validate
node --check site/tla/app.js
node --check site/tla/model-data.js
```

`make validate` checks both the lifecycle-document explorer and the TLA+ explorer. It verifies exact generated bundles, aggregate coverage, counterexample receipts, source links, local-only runtime assets, responsive markers, and JavaScript syntax when Node is available.

For local interaction diagnosis:

```bash
make serve
# http://127.0.0.1:8008/tla/
```

Exercise all four models and views, scenario playback, action filtering, keyboard focus, and narrow/mobile layouts. Local rendering is not final publication acceptance.

### 5. Publish and perform external QA

After reviewing the diff, commit and push `main`. Wait for the **Publish Lifecycle Atlas** Pages workflow to succeed, then inspect a cache-busted public URL in a managed external browser:

```text
https://dreamcatcher-tech.github.io/chambers-lifecycle-explorer/tla/?qa=<commit>
```

Minimum deployed checks:

- root Lifecycle Atlas → **TLA+ Model** link works;
- Ark Core Explain/TLC/Properties views render and interact;
- Multi-Ark phase matrix contains reachable dots and selection details;
- Host Cutover shows the complete 11-state chain;
- Baseline Composition shows the exact provenance/admission/effect/upgrade phase chain and optional Vault scenario;
- source and evidence receipts show the expected commit/hash;
- scenario playback can pause/restart;
- browser Back/Forward restores model/view state;
- desktop and narrow/mobile screenshots have no clipping or overlap;
- console has no uncaught error or failed asset request.

## Changing explanatory annotations

Descriptions and walkthroughs may be edited in `scripts/tla_model_annotations.json`, but they must not invent model behavior. Keep names exact and keep the curated/generated distinction visible. TLC may label a transition with a parameterized inner operator rather than the wrapper named directly in `Next`; `sync_tla_visualization.py` therefore rejects every unannotated emitted operator, every annotation that is neither a direct `Next` action nor an emitted operator, and every missing invariant operator.

If the model adds a new state variable or topology that does not fit the current scalar/tuple/action aggregation, add a bounded aggregation mode and tests. Do not introduce an unbounded TLA+ parser or silently drop states to make a diagram look cleaner.

## Canonical-source boundary

This repository remains a public projection. Do not edit the tagged private formal model, downstream Fundamentals diagrams, or architecture-synthesis provenance from the visualization refresh. A visualization can expose a discrepancy, but a modeled semantic change starts as a candidate formal release; downstream source corrections occur in Fundamentals only after the release exists. Both must be rechecked before this projection advances.
