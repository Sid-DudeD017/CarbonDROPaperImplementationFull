# Carbon-aware scheduling research briefing

An offline-capable, keyboard-navigable React/TypeScript presentation for a professor meeting. It separates published paper values from the repository's reproduced results, labels the accepted “DRO” path as a greedy risk-adjusted heuristic, and includes a clearly illustrative scheduling sandbox.

## Run locally

```bash
npm ci
npm run dev
```

Open the local Vite URL. After installation, the presentation itself makes no runtime API calls and works offline. The display font uses a system fallback if Google Fonts are unavailable.

## Build and checks

```bash
npm run typecheck
npm run build
```

There is no added unit test suite. Existing research test outcomes are documented in the appendix and source report; they are not website test results.

## Controls

- Right / Down / Space: next screen
- Left / Up: previous screen
- Home / End: opening / conclusion
- F: fullscreen
- A: technical appendix
- Q: professor Q&A
- Escape: close overlay, then fullscreen
- Click left rail for direct screen selection; every screen has a URL hash (`#s1` … `#s11`)

Controls are ignored while an input, select, textarea, or editable field has focus.

## Evidence and provenance

`scientific-sources.json` maps claim classes and copied assets to the source repository's relative paths. `public/data/` contains the copied tracked CSVs, manifest with its machine-specific absolute input path removed, and 24-hour example input. `public/plots/` contains the 14 tracked author-format plots. No source repository paths are needed at runtime.

Local-only ignored regime artifacts were not copied. The report's 0/48 detector result is labeled local/exploratory. The checkout origin matches the specified repository; active branch `team/clean-author-format-handoff` is at `5c58e609c6fd45d1c85619a24b44d750f66d8d8f`, while the audited reference commit was `3ce8fab3f7ba3987beb2ac75d387c997a6fe8db2`. The branch difference is the addition of the corrected evidence report.
