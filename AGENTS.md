# Agent instructions

This repository publishes a public interactive projection of the private Fundamentals lifecycle sequence authority.

- Treat `source/chambers-lifecycle-sequences.md` as a copied snapshot, never as the architecture authority.
- Update it only with `python3 scripts/sync_source.py <fundamentals-checkout>`; the script must continue to reject uncommitted source bytes.
- Keep every rendered sequence arrow bound to exactly one function-table row. Unknown labels fail closed.
- Preserve the explicit distinction between I3 calls and `wake_engine`, `activate_chamber`, `stop_chamber`, and `deliver_final_reply` as conventional host-boundary code.
- Keep `site/` self-contained and GitHub Pages compatible; do not add CDN/runtime dependencies unless expressly required.
- Before publishing, run:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_data.py --check --print-summary
python3 scripts/validate_site.py
```

- Website changes require browser interaction smoke checks and desktop/tablet/mobile visual QA. Verify the live Pages URL and assets after deployment.
