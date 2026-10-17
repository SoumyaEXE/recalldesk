/**
 * Data layer.
 *
 * Every read tries the live FastAPI backend first (NEXT_PUBLIC_API_BASE,
 * default http://localhost:8000), then falls back to the static fixtures in
 * /fixtures/*.json, and reports which one answered (plus whether the payload
 * is marked `placeholder`) so the shell can show a "Demo data" badge.
 *
 * Writes (POST /api/check, POST corrections) fall back to an in-browser
 * simulation so the static demo still works end to end, clearly labelled.
 */
import { matchItems, parseInventory } from "./match";
import type {
  CardStatus,
  Correction,
  DataSource,
  EvalResults,
  InventoryItem,
  Memory,
  RecallCard,
  RecallRecord,
  ScanDetail,
  ScanSummary,
  WorkflowRun,
  WorkflowStep,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const TIMEOUT_MS = 2500;
const API_RETRY_AFTER_MS = 15_000;
export const DEMO_SHOP_ID = "little-loop";
export const DEMO_SHOP_NAME = "Little Loop Kids Consignment";

export interface Shop {
  id: string;
  name: string;
  short: string;
  kind: string;
  email: string;
  plan: string;
  initials: string;
  tone: "blue" | "orange";
}

/** The two watched demo shops (agent/shops.json). Both are fictional. */
export const SHOPS: Shop[] = [
  { id: "little-loop", name: "Little Loop Kids Consignment", short: "Little Loop", kind: "Kids consignment shop", email: "intake@littleloop.shop", plan: "Shop plan", initials: "LL", tone: "blue" },
  { id: "flip-garage", name: "Flip Garage", short: "Flip Garage", kind: "eBay flipper · household & tools", email: "hello@flipgarage.store", plan: "Shop plan", initials: "FG", tone: "orange" },
];
export const shopById = (id: string) => SHOPS.find((s) => s.id === id) ?? SHOPS[0];

export interface Sourced<T> {
  data: T;
  source: DataSource;
  placeholder: boolean;
}

/* ----- source tracking (drives the "demo data" badge) --------------------- */

export interface SourceState {
  source: DataSource;
  placeholder: boolean;
}
type Listener = () => void;
const listeners = new Set<Listener>();
let current: SourceState | null = null;

function report(source: DataSource, placeholder: boolean) {
  // Sticky toward "demo": once any panel is on fixtures/placeholder, say so.
  const next: SourceState = {
    source: current?.source === "fixture" ? "fixture" : source,
    placeholder: !!current?.placeholder || placeholder,
  };
  if (current && current.source === next.source && current.placeholder === next.placeholder) return;
  current = next;
  listeners.forEach((l) => l());
}

export const dataSourceStore = {
  subscribe(l: Listener) {
    listeners.add(l);
    return () => {
      listeners.delete(l);
    };
  },
  get(): SourceState | null {
    return current;
  },
};

const isPlaceholder = (x: unknown): boolean => {
  if (!x || typeof x !== "object") return false;
  if (Array.isArray(x)) return x.some((v) => v && typeof v === "object" && (v as { placeholder?: boolean }).placeholder === true);
  return (x as { placeholder?: boolean }).placeholder === true;
};

/* ----- fetchers ------------------------------------------------------------ */

let apiDownUntil = 0;

async function fromApi<T>(path: string, init?: RequestInit): Promise<T> {
  if (Date.now() < apiDownUntil) throw new Error("api marked down");
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...init, signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as T;
  } catch (err) {
    if (!(err instanceof Error && err.message.startsWith("HTTP"))) apiDownUntil = Date.now() + API_RETRY_AFTER_MS;
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

const fixtureCache = new Map<string, Promise<unknown>>();
function fromFixture<T>(name: string): Promise<T> {
  let p = fixtureCache.get(name) as Promise<T> | undefined;
  if (!p) {
    p = fetch(`${BASE_PATH}/fixtures/${name}`).then((r) => {
      if (!r.ok) throw new Error(`fixture ${name}: HTTP ${r.status}`);
      return r.json() as Promise<T>;
    });
    p.catch(() => fixtureCache.delete(name));
    fixtureCache.set(name, p);
  }
  return p;
}

async function load<T>(apiPath: string | null, fixture: string, fromFixtureData: (raw: unknown) => T = (r) => r as T, fromApiData: (raw: unknown) => T = (r) => r as T): Promise<Sourced<T>> {
  if (apiPath) {
    try {
      const raw = await fromApi<unknown>(apiPath);
      const data = fromApiData(raw);
      const placeholder = isPlaceholder(raw);
      report("live", placeholder);
      return { data, source: "live", placeholder };
    } catch {
      /* fall through to fixtures */
    }
  }
  const raw = await fromFixture<unknown>(fixture);
  const data = fromFixtureData(raw);
  const placeholder = isPlaceholder(raw) || isPlaceholder(data);
  report("fixture", placeholder);
  return { data, source: "fixture", placeholder };
}

const unwrap = <T,>(key: string) => (raw: unknown): T => (Array.isArray(raw) ? (raw as T) : ((raw as Record<string, unknown>)?.[key] as T) ?? ([] as T));

/* ----- reads --------------------------------------------------------------- */

export function getHealth(): Promise<boolean> {
  return fromApi<unknown>("/api/health").then(
    () => true,
    () => false,
  );
}

let recallsP: Promise<Sourced<RecallRecord[]>> | null = null;
export function getRecalls(): Promise<Sourced<RecallRecord[]>> {
  if (!recallsP) {
    recallsP = load<RecallRecord[]>("/api/recalls", "recalls.json", undefined, unwrap("recalls"));
    recallsP.then(
      () => setTimeout(() => (recallsP = null), 60_000),
      () => (recallsP = null),
    );
  }
  return recallsP;
}

export function getScan(): Promise<Sourced<ScanSummary>> {
  return load<ScanSummary>("/api/scan", "scan_summary.json");
}

export function getScanDetail(recallNumber: string): Promise<Sourced<ScanDetail>> {
  return load<ScanDetail>(
    `/api/scan/${encodeURIComponent(recallNumber)}`,
    "scan_listings.json",
    (raw) => (raw as Record<string, ScanDetail>)[recallNumber] ?? { recall_number: recallNumber, listings: [], placeholder: true },
    (raw) => (Array.isArray(raw) ? { recall_number: recallNumber, listings: raw } : (raw as ScanDetail)),
  );
}

export function getEval(): Promise<Sourced<EvalResults>> {
  return load<EvalResults>("/api/eval", "eval.json");
}

export async function getRuns(): Promise<Sourced<WorkflowRun[]>> {
  const r = await load<WorkflowRun[]>("/api/runs", "runs.json", undefined, unwrap("runs"));
  return { ...r, data: [...simulatedRuns(), ...r.data] };
}

export async function getMemories(shopId = DEMO_SHOP_ID): Promise<Sourced<Memory[]>> {
  const r = await load<Memory[]>(
    `/api/shops/${encodeURIComponent(shopId)}/memories`,
    "memories_by_shop.json",
    (raw) => (Array.isArray(raw) ? (raw as Memory[]) : ((raw as Record<string, Memory[]>)?.[shopId] ?? [])),
    unwrap("memories"),
  );
  if (r.source === "live") return r;
  return { ...r, data: [...readLocalMemories().filter((m) => !m.shop_id || m.shop_id === shopId), ...r.data] };
}

/** This week's card: latest finished in-browser run → API (latest run with a card) → fixture card. */
export async function getLatestCard(shopId: string = DEMO_SHOP_ID): Promise<Sourced<CardStatus>> {
  try {
    const raw = await fromApi<unknown>(`/api/cards/latest?shop_id=${encodeURIComponent(shopId)}`);
    const st = raw as CardStatus & Partial<RecallCard>;
    const status: CardStatus = st.card ? st : (st as Partial<RecallCard>).do_not_sell ? { status: "completed", card: st as unknown as RecallCard, steps: [] } : st;
    if (status.card) {
      const placeholder = isPlaceholder(raw) || isPlaceholder(status.card);
      report("live", placeholder);
      return { data: status, source: "live", placeholder };
    }
  } catch {
    /* no /latest endpoint: try runs */
  }
  try {
    const runs = unwrap<WorkflowRun[]>("runs")(await fromApi<unknown>("/api/runs"));
    const latest = [...runs]
      .filter((r) => r.status === "completed" && (!r.shop_id || r.shop_id === shopId) && (r.card_id || r.workflow_type === "InventoryCheckWorkflow"))
      .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""))[0];
    if (latest) {
      const st = await fromApi<CardStatus>(`/api/cards/${encodeURIComponent(latest.workflow_id)}`);
      if (st.card) {
        const placeholder = isPlaceholder(st) || isPlaceholder(st.card);
        report("live", placeholder);
        return { data: st, source: "live", placeholder };
      }
    }
  } catch {
    /* fall through */
  }
  return fixtureCard(shopId);
}

async function fixtureCard(shopId: string): Promise<Sourced<CardStatus>> {
  const st = await load<CardStatus>(null, "card_status.json");
  if (st.data.card?.shop_id === shopId) return st;
  try {
    return await load<CardStatus>(null, `card_${shopId}.json`, (raw) => {
      const r = raw as CardStatus & Partial<RecallCard>;
      return r.card ? r : { status: "completed", card: r as unknown as RecallCard, steps: [] };
    });
  } catch {
    return st;
  }
}

/* ----- inventory (the shop's own item list; same file the backend reads) ---- */

export interface InventoryRow {
  sku: string;
  name: string;
  brand?: string;
  model?: string;
  notes?: string;
  category?: string;
  price?: string;
}

const inventoryCache = new Map<string, Promise<InventoryRow[]>>();
export function getInventory(shopId: string = DEMO_SHOP_ID): Promise<Sourced<InventoryRow[]>> {
  let p = inventoryCache.get(shopId);
  if (!p) {
    p = fetch(`${BASE_PATH}/demo/inventory_${shopId}.csv`)
      .then((r) => (r.ok ? r.text() : ""))
      .then(parseInventory);
    p.catch(() => inventoryCache.delete(shopId));
    inventoryCache.set(shopId, p);
  }
  return p.then((data) => ({ data, source: "fixture" as DataSource, placeholder: false }));
}

/* ----- health (connected services) ------------------------------------------ */

export interface Health {
  ok: boolean;
  temporal?: boolean;
  temporal_address?: string;
  model?: unknown;
  memory_backend?: unknown;
  keys?: Record<string, boolean>;
  chaos?: unknown;
  data?: Record<string, boolean>;
}
export function getHealthInfo(): Promise<Health | null> {
  return fromApi<Health>("/api/health").catch(() => null);
}

/* ----- writes --------------------------------------------------------------- */

export async function startCheck(items: InventoryItem[], shopId = DEMO_SHOP_ID): Promise<{ workflow_id: string; source: DataSource }> {
  try {
    const res = await fromApi<{ workflow_id: string }>("/api/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ shop_id: shopId, items }),
    });
    report("live", false);
    return { workflow_id: res.workflow_id, source: "live" };
  } catch {
    const sim: SimWorkflow = {
      workflow_id: `sim-inventory-check-${shopId}-${new Date().toISOString().slice(0, 19).replace(/:/g, "-")}-${Math.random().toString(16).slice(2, 6)}`,
      shop_id: shopId,
      items,
      started: Date.now(),
    };
    memorySims.set(sim.workflow_id, sim);
    writeSims([sim, ...readSims()]);
    report("fixture", true);
    return { workflow_id: sim.workflow_id, source: "fixture" };
  }
}

export async function getCardStatus(id: string): Promise<Sourced<CardStatus>> {
  const sim = findSim(id);
  if (sim) return { data: await simulateStatus(sim), source: "fixture", placeholder: true };
  try {
    const st = await fromApi<CardStatus>(`/api/cards/${encodeURIComponent(id)}`);
    const placeholder = isPlaceholder(st) || isPlaceholder(st.card);
    report("live", placeholder);
    return { data: st, source: "live", placeholder };
  } catch {
    return load<CardStatus>(null, "card_status.json");
  }
}

export async function postCorrection(c: Correction, shopId = DEMO_SHOP_ID): Promise<{ memory_id: string; source: DataSource }> {
  try {
    const res = await fromApi<{ memory_id?: string; id?: string }>(`/api/shops/${encodeURIComponent(shopId)}/corrections`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(c),
    });
    report("live", false);
    return { memory_id: res.memory_id ?? res.id ?? "(no id returned)", source: "live" };
  } catch {
    const mem: Memory = {
      memory_id: `local_mem_${Math.random().toString(16).slice(2, 8)}`,
      shop_id: shopId,
      text: c.note || `${c.listing_or_item}: ${c.correct_verdict.replace("_", " ")} for recall ${c.recall_number}`,
      recall_number: c.recall_number,
      correct_verdict: c.correct_verdict,
      created_at: new Date().toISOString(),
      placeholder: true,
    };
    writeLocalMemories([mem, ...readLocalMemories()]);
    writeLocalCorrections([{ ...c, memory_id: mem.memory_id }, ...readLocalCorrections()]);
    report("fixture", true);
    return { memory_id: mem.memory_id, source: "fixture" };
  }
}

/* ----- local storage helpers ------------------------------------------------ */

function readLS<T>(key: string): T[] {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T[]) : [];
  } catch {
    return [];
  }
}
function writeLS<T>(key: string, v: T[]) {
  try {
    window.localStorage.setItem(key, JSON.stringify(v.slice(0, 25)));
  } catch {
    /* storage blocked — still works for this page view */
  }
}
const MEM_KEY = "recalldesk:local-memories";
const COR_KEY = "recalldesk:local-corrections";
const SIM_KEY = "recalldesk:sim-workflows";
const readLocalMemories = () => (typeof window === "undefined" ? [] : readLS<Memory>(MEM_KEY));
const writeLocalMemories = (v: Memory[]) => writeLS(MEM_KEY, v);
export type LocalCorrection = Correction & { memory_id: string };
export const readLocalCorrections = () => (typeof window === "undefined" ? [] : readLS<LocalCorrection>(COR_KEY));
const writeLocalCorrections = (v: LocalCorrection[]) => writeLS(COR_KEY, v);

/* ----- in-browser InventoryCheckWorkflow simulation -------------------------- */

interface SimWorkflow {
  workflow_id: string;
  shop_id: string;
  items: InventoryItem[];
  started: number;
}
const memorySims = new Map<string, SimWorkflow>();
const readSims = () => (typeof window === "undefined" ? [] : readLS<SimWorkflow>(SIM_KEY));
const writeSims = (v: SimWorkflow[]) => writeLS(SIM_KEY, v.slice(0, 10));
const findSim = (id: string) => memorySims.get(id) ?? readSims().find((s) => s.workflow_id === id);
export const isSimulated = (id: string) => id.startsWith("sim-");

interface Planned {
  name: string;
  start: number;
  end: number;
  failAt?: number;
  error?: string;
  note?: (n: number) => string;
}

function plan(itemCount: number): Planned[] {
  const check = Math.min(5200, 1400 + itemCount * 160);
  return [
    { name: "load_shop_memories", start: 200, end: 900, note: () => "Backboard: shop memories retrieved (local demo store)" },
    {
      name: "check_items",
      start: 1000,
      failAt: 2100,
      end: 2100 + 900 + check,
      error: "attempt 1: model returned invalid JSON for 1 pair — retried after 900 ms backoff",
      note: (n) => `${n} item${n === 1 ? "" : "s"} × top-5 recalls (BM25) · heuristic rules in-browser`,
    },
    { name: "scan_ebay_store", start: 3100 + check, end: 3800 + check, note: () => "source=snapshot (static demo, no SerpApi call)" },
    { name: "compose_card", start: 3900 + check, end: 4500 + check },
    { name: "publish_card", start: 4600 + check, end: 5000 + check },
  ];
}

const iso = (ms: number) => new Date(ms).toISOString();

function stepsAt(sim: SimWorkflow, now: number): { steps: WorkflowStep[]; done: boolean } {
  const el = now - sim.started;
  const p = plan(sim.items.length);
  const steps = p.map((s): WorkflowStep => {
    const note = s.note?.(sim.items.length) ?? null;
    if (el < s.start) return { name: s.name, status: "pending", attempt: 0, started_at: null, ended_at: null };
    if (s.failAt !== undefined && el < s.failAt) return { name: s.name, status: "running", attempt: 1, started_at: iso(sim.started + s.start), ended_at: null, note };
    if (s.failAt !== undefined && el < s.failAt + 900)
      return { name: s.name, status: "retrying", attempt: 1, started_at: iso(sim.started + s.start), ended_at: null, error: "Invalid JSON from model — backing off 900 ms", note };
    const attempt = s.failAt !== undefined ? 2 : 1;
    if (el < s.end) return { name: s.name, status: "running", attempt, started_at: iso(sim.started + s.start), ended_at: null, error: s.error, note };
    return { name: s.name, status: "completed", attempt, started_at: iso(sim.started + s.start), ended_at: iso(sim.started + s.end), error: s.error, note };
  });
  return { steps, done: el >= p[p.length - 1].end };
}

async function simulateStatus(sim: SimWorkflow): Promise<CardStatus> {
  const { steps, done } = stepsAt(sim, Date.now());
  if (!done) return { status: "running", steps, workflow_id: sim.workflow_id, placeholder: true };
  const { data: recalls } = await getRecalls();
  const { data: memories } = await getMemories(sim.shop_id);
  const card = matchItems({
    items: sim.items,
    recalls,
    corrections: readLocalCorrections(),
    memories,
    shopId: sim.shop_id,
    shopName: shopById(sim.shop_id).name,
    workflowId: sim.workflow_id,
    generatedAt: iso(sim.started + plan(sim.items.length).at(-1)!.end),
  });
  const compose = steps.find((s) => s.name === "compose_card");
  if (compose) compose.note = `${card.do_not_sell.length} DO NOT SELL · ${card.check_label.length} CHECK LABEL · ${card.applied_memories.length} memories applied`;
  return { status: "completed", steps, card, workflow_id: sim.workflow_id, placeholder: true };
}

function simulatedRuns(): WorkflowRun[] {
  if (typeof window === "undefined") return [];
  const now = Date.now();
  return readSims().map((sim) => {
    const { steps, done } = stepsAt(sim, now);
    return {
      workflow_id: sim.workflow_id,
      workflow_type: "InventoryCheckWorkflow",
      shop_id: sim.shop_id,
      status: done ? "completed" : "running",
      steps,
      started_at: iso(sim.started),
      ended_at: done ? iso(sim.started + plan(sim.items.length).at(-1)!.end) : null,
      retries: steps.filter((s) => s.attempt > 1).length,
      placeholder: true,
    };
  });
}
