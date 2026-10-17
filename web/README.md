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
| Route | What it is |
|---|---|
| `/` | **Overview**: KPI row (new recalls this Thursday, items checked, do not sell, check label), this week's card as a table (row → item-vs-recall drawer), next-sweep countdown (Temporal schedule), posted this Thursday, eBay teaser, activity feed |
| `/inventory` | The shop's items with verdict pills, Status/Category filters, **Import CSV** / **Paste items** dialogs, live `InventoryCheckWorkflow` step panel, item drawer with "Not a match? Correct this" (Backboard memory + toast). `?new=1` opens the paste dialog |
| `/recalls` | Every CPSC recall since Jul 18; tiles (151 / 48 children's / 73 with the model no. only in the fine print, from `ids_only_in_description`); drawer with CPSC text (IDs highlighted) vs extracted spec, where to look, remedy. `?open=<recall #>` |
| `/ebay` | eBay monitor: searches, listings seen, flagged, human-verified (0: no human review yet); per-recall rows expand into listing cards (seller hash only) |
| `/cards` | Weekly card history + the printable notice (prints on exactly one Letter page) |
| `/memory` | Shop memory (Backboard corrections), applied-this-week counts, remove (UI only: no delete API) |
| `/runs` | Temporal runs table + drawer: waterfall, activity timeline, retry / crash-resume badges, "Open in Temporal UI". `?open=<workflow id>` |
| `/lab` | Model Lab: accuracy with CI, risky caught vs false alarms, cost / 1k, latency, confusion matrices, loss curve (or "training pending"), paired tests |
| `/settings/services` | Connected services from `/api/health` (Tinker, SerpApi, Backboard, Temporal, Sentry, CPSC) |
| `/settings/billing`, `/settings/team` | Demo-only billing (transaction history, subscription preview) and team pages, clearly badged |
| `/about` | Pricing ($15/mo Shop, $49 Event) and what this is not |

Old routes redirect: `/check` → `/inventory`, `/scan` → `/ebay`, `/settings` → `/settings/services`.
Global: ⌘K / Ctrl+K (or `/`) command palette (pages, recall #, brand, model number), shop switcher (Little Loop / Flip Garage;
`?shop=` wins), notifications bell (this Thursday's recalls), theme toggle in the account menu (light is the default).

## Data
Every read tries the API first, then `public/fixtures/*.json`. The sidebar chip says **Live API** only when the API answered
and nothing was marked `"placeholder": true`; otherwise **Demo data**. With the API down, `/inventory` runs an in-browser simulation of
`InventoryCheckWorkflow` (same step names, one retried step) using deterministic identifier rules, and corrections are stored in
localStorage with a `local_mem_*` id. Both are labelled.

Fixtures: recalls are real CPSC records (since 2026-07-18). Listings, scan counts, eval numbers, runs and memories are placeholders.
When the backend writes `shared/fixtures/*.json`, copy them over `public/fixtures/`.

## Design
Framed desktop app: soft gray canvas, one rounded white frame, a 248px left sidebar (drawer below 1024px), a top bar, KPI cards
and table cards. Inter for UI with tabular numerals, IBM Plex Mono for model numbers and workflow ids. Neutral cool grays, product
blue (`#1D4ED8`) for primary actions, and three reserved signals with tinted pills: **Do not sell** (red, octagon glyph),
**Check label** (amber, triangle glyph), **Clear** (green, circle glyph); children's recalls are a blue pill. Every number that
is a placeholder carries a dashed "Demo" badge. Tokens live in `styles/recalldesk.css` (`bg-canvas`, `bg-frame`, `bg-card`,
`bg-subtle`, `border-line`, signal + chart tokens; dark mode redefines them); BoardUI's `theme.css` is untouched.
Chart colours were run through the dataviz validator (blue `#2563eb` / orange `#ea580c` light, `#3b82f6` / `#ea580c` dark).

The printable card keeps its own "safety notice" look (paper, Barlow Condensed headings, hazard tape) in both themes. In print
the pull lists flow into two columns and `RecallCard` measures itself under print media and zooms to fit one Letter page.

### BoardUI components used
Installed from the BoardUI registry (`https://www.boardui.com/r/<name>.json`, source-owned under `components/`):
**Button / ButtonLink, CloseButton, IconButton, Dropdown** (filter pills, shop switcher, account menu, notifications),
**Select, SegmentedControl, Tabs, Tooltip, Kbd, Avatar, Badge, Chip, StatusDot, Pagination, Input, Textarea, File Upload**
(Import CSV), **Notification + NotificationViewport** (toasts), **ThemeToggle**, **Stat Cards** (`application/dashboard/stat-cards.tsx`,
the recipe behind `components/ui/kpi.tsx`), and the **Sidebar** block's workspace-switcher / nav-row / account-menu recipes
(adapted in `components/shell/`). Overlays (drawer, dialog, ⌘K) are React Aria `ModalOverlay`/`Modal`/`Dialog` styled with the
BoardUI menu surface. App-level pieces: `components/ui/` (Card, pills, KPI, DataTable with sort + stacked mobile cards, drawer,
dialog, toast store), `components/shell/` (sidebar, top bar, command palette).

## Screenshots
`npm run shots` → `../docs/screenshots/` (every page at 1440 and 390, light and dark, plus `check-done`, `inventory-drawer`,
`recalls-expanded`, and `home-print.png/.pdf`, which must be one page). `node scripts/blog-shots.mjs` → `../docs/blog-shots/`
(`overview-1440`, `home-card-1440`, `home-card-390`, `inventory-1440`, `inventory-drawer-1440`, `check-done-1440`,
`recalls-expanded-1440`, `ebay-1440`, `runs-crash-1440`, `lab-1440`, `billing-1440`, `services-1440`, plus label UI and Temporal
UI shots). Both wait for CPSC photos to finish loading before capturing. `bash ../docs/regen_media.sh --shots-only` runs the
whole stack for the blog set.
