# Agent instructions

This repository publishes a public interactive projection of two private Fundamentals sequence authorities.

- Treat `source/chambers-lifecycle-sequences.md` and `source/cardflow-filesystem-lease-sequences.md` as copied snapshots, never as architecture authorities.
- Update both only with `python3 scripts/sync_source.py <fundamentals-checkout>`. The script must continue to reject dirty, uncommitted, ahead, or behind source state.
- Keep `source/manifest.json` as the sole source registry and bind each copied document to its own last-touch commit, byte count, SHA-256, and exact private GitHub URL.
- Keep every rendered sequence arrow bound to exactly one row in that document's function table. Unknown labels fail closed.
- Preserve document boundaries in navigation, URL state, search results, actor roles, function catalogs, and provenance. Never merge Chambers and Cardflow into an unlabeled selector.
- Preserve Chambers' explicit distinction between I3 calls and `wake_engine`, `activate_chamber`, `stop_chamber`, and `deliver_final_reply` as conventional host-boundary code. Do not infer Cardflow semantics beyond its source.
- Sequence call selection and playback must not auto-pan the canvas. User-controlled pan/scroll is deliberate and must be preserved across selection changes.
- Keep `site/` self-contained and GitHub Pages compatible; do not add CDN/runtime dependencies unless expressly required.
- Before publishing, run:

```bash
make validate
node qa/browser-smoke.js
```

- Website changes require browser interaction smoke checks and desktop/tablet/mobile visual or geometry QA. Verify both document workspaces and the live Pages URL/assets after deployment.
