# Lifecycle Atlas

A polished, playable explorer for the authoritative Chambers lifecycle and Cardflow filesystem-lease sequence documents.

**Live site:** <https://dreamcatcher-tech.github.io/chambers-lifecycle-explorer/>

## What it provides

- **Two explicit document workspaces** — switch between **Chambers** and **Cardflow** without mixing their actors, calls, functions, or provenance. Desktop uses document tabs; tablet/mobile uses a document selector.
- **Legible Chambers startup ladder** — Chambers opens with **Engine cold start**, then **Core bootstrap**, then **Ordinary activation**. Engine cold start conditionally creates an Engine only when none is ready, uses pinned libp2p Noise plus HPM admission instead of a redundant same-key identity challenge, and shows Image Materializer/`containerd` exact cache, pull, and bounded-import paths. Core bootstrap starts the first **Persistence** Chamber from a Boot Seed before restoring Supervisor. Ordinary activation reads durable Realization/launch data through Persistence, while OCI content and snapshots stay on a dedicated disposable containerd slice. `containerd` never calls Persistence or I3 directly.
- **Trace** — custom sequence lanes with play/pause, reset, step, scrub, actor focus, call-type filtering, zoom, keyboard shortcuts, touch gestures, and document-aware deep links. The compact step/route/function summary stays structurally stable while full branch and note context remains in the selected-call inspector. The diagram participates in the primary page flow instead of owning a nested vertical scrollbar; selected calls receive only the minimum vertical reveal required, while horizontal pan is preserved exactly. Actor labels stay pinned below the page controls and track horizontal pan while the page moves through a long diagram. The selected-call inspector keeps a constant height while exploring one sequence.
- **Browser navigation** — meaningful document, sequence, view, call, and function changes populate browser history, so Back and Forward restore the corresponding app state and primary-page position. A continuous scrub creates one navigable entry rather than corrupting the entry it started from.
- **Map** — an actor relationship graph with directed, frequency-weighted connections and call drill-down.
- **Functions** — the complete function table for the selected document, including implementation status and diagram usage.
- **Cross-document search** — find a sequence or function in either authority and move directly into its document workspace.
- **Exact provenance** — every generated call resolves to a function-table row; each snapshot is bound to its Fundamentals source commit and SHA-256.
- **Source jump** — the snapshot card and footer open the exact private GitHub source document in a new page for viewers with repository access.
- **No runtime dependencies** — the published artifact is plain HTML, CSS, JavaScript, and generated data. No CDN or Mermaid runtime is needed.

## Source and update model

The authoritative sources are the private Fundamentals checkout:

```text
dreamcatcher-tech/fundamentals
├── docs/chambers-lifecycle-sequences.md
└── docs/cardflow-filesystem-lease-sequences.md
```

This public repository contains intentional committed snapshots. The synchronization path is fail-closed: every registered document must be committed, the Fundamentals checkout must be clean and synchronized with its upstream, every diagram call must resolve to that document's function table, and the generated browser bundle must exactly match the copied sources.

The durable maintainer/agent procedure is [`docs/source-refresh-runbook.md`](docs/source-refresh-runbook.md). It covers routine refreshes, semantic review, browser/publication proof, and deliberate onboarding of a new sequence-document family.

```bash
git -C ../fundamentals fetch --all --prune
git -C ../fundamentals pull --ff-only
python3 scripts/sync_source.py ../fundamentals
make validate
node --check site/app.js
git add source site/data.js
git commit -m "docs: sync lifecycle sequence sources"
git push
# wait for Pages, then inspect the cache-busted public URL in a managed external browser
```

`sync_source.py` copies every deliberately registered authority, writes `source/manifest.json`, rebuilds `site/data.js`, and validates the publication. Public sequence order follows the explicit metadata registry while stable sequence IDs preserve deep links. A push to `main` repeats validation and republishes GitHub Pages.

### Adding another Fundamentals sequence authority

New documents are not auto-discovered, because registration copies private source bytes into a public repository and browser payload. Add the source explicitly to `scripts/sync_source.py::DOCUMENTS`, add its workspace and sequence metadata to `scripts/build_data.py::DOCUMENT_CONFIGS`, then generalize the exact document/count checks, UI theme/wording, tests, and QA fixtures described in the runbook. If the source uses a new Markdown/Mermaid shape, extend the parser with exact semantic fixtures rather than hand-authoring browser data.

## Local nonvisual diagnosis

```bash
python3 -m http.server 8008 --directory site
# open http://127.0.0.1:8008/
```

This can support static or nonvisual diagnosis, but it is not visual acceptance. Push the reviewable
change first and use a cache-busted GitHub Pages URL in a managed external browser for visual QA.

Useful document-aware deep links:

```text
?doc=chambers&diagram=selection-rollback&call=selection-rollback-call-5
?doc=cardflow&diagram=queue-inspect-wait
?doc=cardflow&diagram=release-handoff&view=map
?doc=cardflow&view=functions&function=cardflow%3A%3Aresource%3A%3Aclaim
```

## Architecture

```text
source/manifest.json
source/chambers-lifecycle-sequences.md ─┐
                                        ├─> scripts/build_data.py
source/cardflow-filesystem-lease-sequences.md ─┘   ├─ parses each function table
                                                    ├─ parses every sequence arrow
                                                    ├─ preserves phases, branches, and notes
                                                    └─ rejects unknown function labels
                                                               │
                                                               ▼
                                                         site/data.js
                                                               │
                                     ┌─────────────────────────┴─────────────────────────┐
                                     ▼                                                   ▼
                              Chambers workspace                                  Cardflow workspace
                              Trace · Map · Functions                             Trace · Map · Functions
```

The parser classifies calls from each source's function table rather than visual guesswork. Chambers keeps
`wake_engine`, Image Materializer/`containerd` calls, `activate_chamber`, `stop_chamber`, and
`deliver_final_reply` as conventional host-boundary calls; the current Cardflow reference is entirely I3.
Cardflow function statuses such as **required** and **contract extension required** are preserved in the
function inspector.

## Verification

```bash
make validate
```

Maintainers may additionally run ignored local Playwright diagnostics from `qa/`; those browser artifacts
are deliberately not published and never substitute for deployed external-browser visual acceptance.
