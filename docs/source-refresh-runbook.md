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

   For Chambers specifically, verify that `HostAgent` is the leftmost lane wherever present. Top-level
   diagrams must not expose containerd, selector-filesystem, volume, CNI, or runsc lanes/calls; those mechanics
   remain encapsulated by `start_ark_core` and typed ordinary Host Agent operations. The public order starts with
   **First Ark Core installation**, **Selected Ark Core cold start**, **Ark Core bootstrap**,
   **Whole-appliance crash recovery**, **Scope-bound child Ark Core activation**, then **Ordinary activation**.
   Preserve existing IDs where semantics persist (`core-installation`, `host-activation`, `core-bootstrap`,
   `boot-crash-repair`, `activation-kernel`, and `core-cutover`); allocate a new ID only for a genuinely new sequence.

   Cold activation must contain `wake_ark_core`, at least one `start_ark_core`, no lower runtime call, and one note
   that the canonical selector is read exactly once. One selected Ark Core Appliance is one OCI image and one gVisor
   task. s6 is PID 1: its one-shot bootstrap seeds private `/run/iii` tmpfs, then its accepted graph starts Engine,
   Persistence, Gateway, and Supervisor in that internal order. s6 never restarts one required member locally; any
   required-process exit or Engine-validated semantic-readiness loss exits the whole task. The loopback Worker Manager at
   `127.0.0.1:49133` admits only exact required workers without a host-donated Persistence stream. After Gateway
   installs fail-closed hooks, ProcMan uses the distinct Ark-private Worker Manager at port `49134` through a direct
   private Core address, with no host port mapping, host-network mode, or UDS relay. Ordinary Chambers remain separate
   and receive no Ark-volume contents.

   The sole mutable Core selector is Persistence-maintained `boot-control/selected.json`. Normal selection is
   `ark::core::stage`, external authorization, `persistence::core::commit`, then `ark::core::restart`. Core restart
   stops the complete Ark scope tree and starts one fresh appliance. The ordinary Gateway route sequence remains
   separate and contains ordinary Persistence CAS plus `routing::fence/install/reopen`, never Core selection or
   restart.

   Same-selection recovery is whole-appliance only: `recover_ark_tree` reaps every descendant and the failed Core,
   releases that scope's attachments, and invokes `start_ark_core` from the cached exact plan without rereading or
   changing selection. Persistence-, Gateway-, and Supervisor-local repair must not reappear. Complete Core
   replacement shows one staged image, atomic selector commit, complete scope restart, one fresh Core start, route
   reconstruction, and a context-preserving failure branch. Automatic fallback remains one exact monotonic,
   compatibility-qualified recovery selector before ordinary admission or irreversible effects.

   Scope-bound child activation must show `ark::core::activate` creating a separate selector, test volume, private
   network, Core task, and ProcMan registration. The authenticated child connection supplies scope and caller-supplied
   routing fields are rejected. The child may create only its own descendants, each with a separate task attachment
   to the child network. Never project cross-scope forwarding, caller-selected scope, sibling task handle, shared Ark
   volume contents, or generic containerd authority. The same primitive supports candidate Core rehearsal and several
   independent root Arks on one physical host.

   Preserve the source's proof distinction: 22/22 checks establish bounded mechanisms on real runsc/Linux networking,
   selector/LKG fixtures, directory-backed volume fences, and the superseded Engine-owned fatality mechanism. They do
   not establish s6 whole-appliance fatality, production containerd/CNI-plugin, storage-driver, packaging, deployment,
   or operational acceptance.

   Builder remains separately sandboxed. The Core's accepted residual risk—container-root can reach Persistence's
   mounted data—must not be mislabeled as process isolation or silently restored as a hard four-sandbox constraint.

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
