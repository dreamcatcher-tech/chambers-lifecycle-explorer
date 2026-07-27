# Agent instructions

This repository publishes a public interactive projection of deliberately registered private Fundamentals sequence authorities.

- Load and follow `docs/source-refresh-runbook.md` whenever a Fundamentals sequence document changes, a source snapshot or generated bundle is stale, or a new sequence-document family must become a Lifecycle Atlas workspace.
- Treat every `source/*.md` file as a copied snapshot, never as architecture authority. The private `dreamcatcher-tech/fundamentals` source documents remain canonical.
- Never edit `source/manifest.json` or `site/data.js` by hand. Refresh registered sources only with `python3 scripts/sync_source.py <fundamentals-checkout>`.
- Existing source registration lives in `scripts/sync_source.py::DOCUMENTS`; matching workspace/parser metadata lives in `scripts/build_data.py::DOCUMENT_CONFIGS`. `source/manifest.json` is generated provenance, not an authoring registry.
- Register new documents deliberately. Do not glob and publish every Fundamentals sequence file: registration copies exact source bytes into this public repository and browser payload.
- Before refresh, fetch/pull both repositories and require Fundamentals to be clean, committed, branch-attached, and synchronized with its tracking remote. Do not project ambiguous local bytes.
- Bind each copied document to its own last-touch commit, byte count, SHA-256, and exact private GitHub URL.
- Keep every rendered sequence arrow bound to exactly one row in that document's function table. Unknown labels and cross-document resolution fail closed.
- Require exactly one source-owned `## Dictionary` table per registered document. Generate term definitions and related-term edges from it, preserve exact source-line links, and fail closed on duplicate terms, slug collisions, non-alphabetized rows, or unresolved/cross-document relations.
- Preserve source participant order, calls, control fragments, notes, status markers, and document-level caveats. `sequenceMeta` insertion order is the intentional public display order; keep published sequence IDs stable when editorial order changes. Totals are insufficient: explicitly verify note-only branches and nested control context.
- Preserve document boundaries in navigation, URL state, search results, actor roles, function and Dictionary catalogs, and provenance. Never mix sources in an unlabeled selector.
- Preserve Chambers' explicit distinction between I3 calls and the source-marked conventional host calls `install_boot_seed`, `wake_core`, `deliver_final_reply`, `containerd_*`, and `start_core_process`. The typed `chamber::*` and `bootset::*` calls are I3 functions registered by the Host Agent after Core readiness. Do not infer semantics or implementation status beyond each source.
- For Chambers, preserve the Host Agent as the leftmost lane whenever present. `containerd` follows it only in the installation, cold-start, reboot, selection, and live-cutover sequences that expose the standard backend; all ordinary containerd/runsc-shim detail stays encapsulated by `chamber::activate` and `chamber::stop`. Every drawn `containerd_*` call originates at `HostAgent`, and no removed Procman, Image Materializer, or direct-runtime lane may reappear. Preserve the protected product-durable boot namespace and authoritative `dreamcatcher/core:current` Boot-set tag separately from the reconstructable ordinary runtime namespace. Cardflow remains governed by its own source vocabulary until that authority is reconciled.
- Never auto-pan the sequence canvas horizontally or center selected calls. A selected call may use the primary page scrollbar for the minimum vertical reveal needed to become fully visible; preserve `scrollLeft` exactly and do not move when the call is already vertically visible. The sequence graphic itself must not own a vertical scrollbar.
- While the primary page scroll passes through a sequence diagram, keep a non-interactive actor-label strip sticky below the page's sticky controls and horizontally synchronized with the diagram. Account for this physical overlay when minimally revealing selected calls.
- Keep dynamic structural panels stable during within-sequence exploration. The top selected-call summary contains only step, route, and function; branch and note detail belongs in the inspector so wrapping context cannot shift the Trace. The selected-call I3/host inspector reserves the maximum height needed by the active sequence, and its function metadata uses compact keyed values rather than grid-stretched pills; a sequence change may legitimately establish a different height.
- Meaningful document, sequence, view, call, function, and Dictionary-term navigation must create browser-history entries. Back/Forward must restore each URL-addressed application state and its recorded primary-page scroll position; automatic playback may replace the current entry rather than flooding history. Treat one continuous scrub as one entry, and never let filtering silently change a selected call, function, or term without matching URL/history state.
- Local SVG controls own their Enter/Space keys and must retain focus across sequence rerenders. Global shortcuts must ignore handled events and native/ARIA interactive controls.
- SVG branch-context labels must be laid out independently of the centered `I3` / `HOST BOUNDARY` kind label; long branch text may truncate, but the two labels must never overlap.
- Keep `site/` self-contained and GitHub Pages compatible; do not add CDN/runtime dependencies unless expressly required.
- Before deployment, run the deterministic non-visual gate:

```bash
make validate
node --check site/app.js
git diff --check
```

- For website changes, commit and push the bounded change, wait for GitHub Pages, and use the cache-busted public deployment as the preview. Perform visual acceptance in a managed external browser, not locally hosted Chrome against localhost; the site does not need to be production-ready for this loop. Exercise desktop/tablet/390px/320px, every registered workspace, the densest sequence/map, Dictionary search/detail/related-term/source-line flows, deep links, keyboard/accessibility behavior, console errors, and live asset readback. If QA finds a defect, push another bounded fix and repeat against Pages.
