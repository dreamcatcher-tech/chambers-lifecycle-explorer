# Fundamentals sequence source refresh runbook

Use this runbook whenever a registered Fundamentals sequence authority changes, or when a new Fundamentals sequence-document family must become a Lifecycle Atlas workspace.

## Authority and publication boundary

- `/opt/data/repos/fundamentals` is the private architecture authority.
- `/opt/data/repos/chambers-lifecycle-explorer` is a public generated projection.
- Files under `source/` are exact committed snapshots, not editable authority.
- `source/manifest.json` and `site/data.js` are generated outputs. Never repair either by hand.
- Publication is deliberate. Do **not** discover and publish every matching Fundamentals file automatically: registering a document copies its bytes into a public repository and browser payload.

The current registered authorities are:

| Workspace | Fundamentals authority | Public snapshot |
| --- | --- | --- |
| Chambers | `docs/chambers-lifecycle-sequences.md` | `source/chambers-lifecycle-sequences.md` |
| Cardflow | `docs/cardflow-filesystem-lease-sequences.md` | `source/cardflow-filesystem-lease-sequences.md` |

The registration surfaces of record are:

- `scripts/sync_source.py::DOCUMENTS` — private source path and public snapshot name.
- `scripts/build_data.py::DOCUMENT_CONFIGS` — workspace copy, function-table heading, sequence metadata, ordering, and theme.
- each registered source's single `## Dictionary` table — canonical term, definition, and document-local related-term edges.
- `source/manifest.json` — generated provenance for the registered set; it is not an authoring registry.

## Refresh an already registered authority

1. Read `fundamentals/AGENTS.md`, this repository's `AGENTS.md`, this runbook, and the changed source document.
2. Synchronize both repositories before trusting local state. Do not overwrite dirty work.

   ```bash
   git -C ../fundamentals status --short --branch
   git -C ../fundamentals fetch --all --prune
   git -C ../fundamentals pull --ff-only
   git status --short --branch
   git fetch --all --prune
   git pull --ff-only
   ```

3. Require the Fundamentals checkout to be clean, on a branch, and exactly synchronized with its tracking branch. Commit and push authoritative changes in Fundamentals before projecting them.
4. Run the one supported refresh command from the Atlas repository:

   ```bash
   python3 scripts/sync_source.py ../fundamentals
   ```

   It copies every registered authority, regenerates `source/manifest.json` and `site/data.js`, and runs parser/static validation. If it fails, fix the source/parser/config contract; never hand-edit generated output to make it pass.

5. Inspect the generated diff. For each document, verify:
   - snapshot bytes equal the authoritative file;
   - manifest `path`, `sourceCommit`, `sourceTimestamp`, `documentSha256`, and `documentBytes` describe those exact bytes;
   - the source URL names that document's last-touch commit and private repository path;
   - every Mermaid call resolves to exactly one row in that document's function table;
   - the one `## Dictionary` table parses exactly, keeps unique alphabetized terms, resolves every related term within that document, and preserves exact source-line coordinates;
   - participant order, message direction, branches, loops/options, notes, implementation markers, and document-level caveats retain their source meaning;
   - public sequence order follows the deliberate `sequenceMeta` registry order while every published sequence ID remains stable;
   - document navigation, search, function and Dictionary catalogs, actor roles, and provenance remain scoped to the selected authority.

   For Chambers specifically, verify that `HostAgent` is the leftmost lane wherever present. `containerd`
   follows only in the installation, cold-start, reboot, selection, and live-cutover diagrams that expose the
   standard backend, and every drawn `containerd_*` call originates at `HostAgent`. Ordinary activation and
   stopping use the typed I3 functions `chamber::activate`, `chamber::inspect`, and `chamber::stop`; they do
   not expose Image Materializer, direct `runsc`, or raw runtime lanes. The public Chambers order starts with
   **First core installation**, **Core image cold start**, **Core process bootstrap**, **Reboot selected Core**,
   and **Ordinary activation**, while preserving the published IDs for those renamed sequences. Core image
   cold start contains exactly one `containerd_task_start` under “No matching ready Core task exists,” no
   application-level identity-attest call, and no build, mutable pull, recency, or fallback branch.

   The Host Agent is the sole containerd client and sole writer of the protected
   `dreamcatcher/core:current` image record. That record selects one exact immutable Boot-set artifact whose
   only runnable member is one Core image; Engine, Persistence, and Supervisor start locally in one gVisor
   Core Chamber. The selected and predecessor closures are pinned in the product-durable boot namespace,
   while the ordinary runtime namespace remains reconstructable. Persistence remains the sole normal writer
   of ordinary `current[name]`, and Engine route state never selects the Core. `bootset::stage`,
   `bootset::inspect`, and `bootset::select` perform lower-host Core selection without route-group promotion.
   Core-local processes use the exact local registration contract rather than intra-Core PeerIds; ordinary
   Chambers retain fresh PeerIds and reconnect across Core cutover to the host-custodied stable Engine
   identity under a fresh boot epoch. Builder remains a separately sandboxed ordinary Chamber; an accepted
   first Builder image may be imported by the Boot Seed, but build never enters Host Agent or cold start.
   Missing, malformed, unaccepted, or mismatched selected boot state fails closed; only an externally
   accepted one-use Boot Seed may establish a provably unenrolled Ark.

   Totals alone are not semantic proof. In particular, inspect note-only `alt`/`else` branches and nested control fragments; a note must not be attached to an unrelated nearby call merely because its line number is close.

6. Run the deterministic pre-deployment gate without treating a locally hosted browser as visual evidence:

   ```bash
   make validate
   node --check site/app.js
   git diff --check
   ```

7. Commit only the intended projection changes, push `main`, and wait for `Publish Lifecycle Atlas`. Read back cache-busted live HTML/assets and require them to match the committed publication bytes.
8. Use a managed external browser against the deployed GitHub Pages URL for visual and interaction acceptance. Do not use locally hosted Chrome against localhost as the visual-QA substitute; Pages is the iterative preview even while the site is not production-ready. Inspect desktop, tablet, 390px mobile, and 320px mobile; check dense and bidirectional maps, Dictionary search/detail/related-term navigation, exact-line term links, branch/kind labels, touch targets, initial context, and page-level overflow—not only the first/default sequence. If QA finds a defect, push another bounded fix and repeat against Pages.

   External browser checks must exercise every registered workspace and sequence. For call selection, assert that the requested call becomes current, the top step/route/function summary keeps one constant height with no duplicated branch pills, `scrollLeft` remains unchanged, an already visible call does not move the page, and an off-screen call uses the primary page scrollbar for only the minimum top/bottom reveal required. Confirm that full branch and note context remains present in the inspector and that its keyed function metadata never stretches to the context-column height. Sweep every SVG row for branch-context versus `I3` / `HOST BOUNDARY` label collisions; branch text may truncate in the diagram but must retain its full value in the inspector. The diagram must not own a vertical scrollbar. While a long diagram crosses the page viewport, assert that its sticky actor labels remain below sticky page controls, mirror every actor, stay horizontally aligned after panning, and are included in selected-call occlusion geometry. Also sweep representative calls to prove the active sequence's inspector height is stable and unclipped. Exercise reset, sidebar/mobile/search selection, a real scrub with a frame between `input` and `change`, next/previous, playback restart, Map and Functions drill-down, document switching, URL history with exact Back/Forward scroll restoration, filter-induced selection, keyboard focus retention, shortcut isolation on local controls, and accessibility roles.

## Register a new sequence-document family

New documents are deliberately onboarded; they are not auto-published by filename.

### 1. Qualify the source contract

The authoritative document must be committed in Fundamentals and have a stable structure the deterministic parser can support:

- displayed sequence sections use `##` headings;
- each displayed sequence contains a fenced Mermaid `sequenceDiagram`;
- participants are declared before use;
- call messages name function IDs in backticks;
- one function-table section defines every called function exactly once, with invocation path and contract columns;
- one `## Dictionary` section contains exactly one `Term | Definition | Related terms` table; terms are unique and alphabetized, and semicolon-separated related terms resolve within that document;
- status markers and document-level maturity/runtime caveats have explicit source semantics.

If a new authority uses a different structure, generalize the parser with exact fixtures and fail-closed tests. Do not introduce hand-authored browser data as a fallback.

### 2. Register source and workspace metadata

1. Add one entry to `scripts/sync_source.py::DOCUMENTS` with a stable lowercase `id`, Fundamentals-relative `path`, and unique `snapshotPath`.
2. Add the document's sequence metadata and one matching `scripts/build_data.py::DOCUMENT_CONFIGS` entry. Record:
   - display name/title/subtitle/description;
   - exact function-table heading;
   - source-defined status vocabulary and caveats;
   - stable sequence IDs, short titles, summaries, questions, and status labels;
   - a supported accent/theme.
3. Keep IDs stable after publication; they are URL contracts.
4. Review generic UI assumptions:
   - `site/app.js` renders tabs/selectors/search from `atlas.documents`, but new state transitions still need browser coverage;
   - add a `body[data-document="<id>"]` theme in `site/styles.css` when the document needs a distinct accent;
   - update static product/brand wording in `site/index.html` where the previous two-document wording is no longer accurate;
   - ensure desktop navigation wraps and mobile selection remains usable with the larger document count.
5. Generalize exact-two validation where necessary. Update `scripts/validate_site.py`, `tests/test_build_data.py`, README deep links/counts, and QA fixtures so the registered document order, IDs, source binding, expected sequences, and source-defined statistics are checked intentionally.
6. Run `python3 scripts/sync_source.py ../fundamentals`, then follow the complete validation, visual QA, commit, deployment, and live-readback gates above.

### 3. New-document acceptance checks

Do not publish until all are true:

- the snapshot and manifest bind the exact private source bytes and last-touch commit;
- every arrow/function/table relationship is closed and document-local;
- every Dictionary definition and related-term edge is source-derived, closed, and document-local;
- control fragments and note-only branches retain exact context;
- unmarked and marked implementation statuses mean only what that document defines;
- a direct `?doc=<id>` URL opens the intended workspace without fallback;
- all sequences work in Trace, Map, and Functions views;
- cross-document search enters the right workspace and URL;
- accessibility-tree controls retain native button/combobox semantics;
- responsive QA includes the densest sequence/map, not merely the default;
- CI and the live Pages artifact pass before completion is reported.

## Publication report

Report the authoritative source commit(s), Atlas commit, registered document/sequence/call/function counts, validation commands, Pages workflow URL, live workspace URL, and any remaining semantic limitation. Never claim that a passing static validator establishes architecture or runtime acceptance.
