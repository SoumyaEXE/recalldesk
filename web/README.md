# RecallDesk web

Next.js 16 (App Router, TypeScript, Tailwind v4) with BoardUI source-owned components. Data shapes: [../CONTRACT.md](../CONTRACT.md), mirrored in `lib/types.ts`.

```bash
npm install
npm run dev                       # http://localhost:3000, API at NEXT_PUBLIC_API_BASE (default http://localhost:8000)
npm run build && npm start        # production
STATIC_EXPORT=1 npm run build     # fully static demo in out/ (renders from public/fixtures)
npm run typecheck && npm run lint
npm run fixtures                  # rebuild public/fixtures from live CPSC data
npm run shots                     # ../docs/screenshots (server on :3000; BASE=..., OFFLINE=1, CLEAN=1)
```

## Pages
`/` this week's card (printable) · `/check` paste/CSV items, live workflow steps, corrections · `/recalls` CPSC text vs extracted spec ·
`/scan` the eBay scan · `/lab` Model Lab · `/runs` Temporal runs · `/about` pricing and limits.

## Data
Every read tries the API first, then `public/fixtures/*.json`. The sidebar chip says **Live API** only when the API answered
and nothing was marked `"placeholder": true`; otherwise **Demo data**. With the API down, `/check` runs an in-browser simulation of
`InventoryCheckWorkflow` (same step names, one retried step) using deterministic identifier rules, and corrections are stored in
localStorage with a `local_mem_*` id. Both are labelled.

Fixtures: recalls are real CPSC records (since 2026-07-18). Listings, scan counts, eval numbers, runs and memories are placeholders.
When the backend writes `shared/fixtures/*.json`, copy them over `public/fixtures/`.

## Design
"Safety notice meets shop ledger." Warm manila neutrals, ledger-ink blue accent, and two reserved signals: **DO NOT SELL** (signal red,
octagon glyph) and **CHECK LABEL** (amber, triangle glyph). Shapes keep the card readable in grayscale print. The card is a physical
notice: it stays ink-on-paper in dark mode and prints as one page with a sign-off line. Type: Public Sans (UI), Barlow Condensed
(notice headings and big numbers), IBM Plex Mono (identifiers). Charts use emphasis encoding (ours in ink blue, others neutral) and a
validated two-series pair for training curves. Tokens live in `styles/recalldesk.css`; BoardUI's `theme.css` is untouched.
