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
- Preserve participant order, calls, control fragments, notes, status markers, and document-level caveats. Totals are insufficient: explicitly verify note-only branches and nested control context.
- Preserve document boundaries in navigation, URL state, search results, actor roles, function catalogs, and provenance. Never mix sources in an unlabeled selector.
- Preserve Chambers' explicit distinction between I3 calls and `wake_engine`, `activate_chamber`, `stop_chamber`, and `deliver_final_reply` as conventional host-boundary code. Do not infer semantics or implementation status beyond each source.
- Sequence call selection and playback must not auto-pan the canvas. Verify both selection correctness and preservation of deliberate user scroll position.
- Keep `site/` self-contained and GitHub Pages compatible; do not add CDN/runtime dependencies unless expressly required.
- Before publishing, run:

```bash
make validate
node --check site/app.js
node qa/browser-smoke.js
node qa/layout-audit.js
```

- Website changes require browser interaction smoke checks and desktop/tablet/390px/320px visual or geometry QA. Exercise every registered workspace, the densest sequence/map, deep links, keyboard/accessibility behavior, and the live Pages URL/assets after deployment.
