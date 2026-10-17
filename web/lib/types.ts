/**
 * Mirrors shared/schema.py (see ../CONTRACT.md). Optional fields marked "UI
 * extension" are not in the contract yet; the UI tolerates their absence.
 */

export type Verdict = "match" | "check" | "no_match";
export type DataSource = "live" | "fixture";

export interface RecallSpec {
  recall_number: string;
  brand: string;
  product_type: string;
  product_name: string;
  model_numbers: string[];
  upcs: string[];
  other_identifiers: string[];
  sold_from: string | null;
  sold_to: string | null;
  colors: string[];
  key_features: string[];
  not_included: string[];
  search_queries: string[];
  is_childrens: boolean;
  hazard_short: string;
  remedy_short: string;
  /** UI extension: where on the product the identifier lives. */
  look_for?: string | null;
  /** UI extension: "teacher" | "heuristic" | "hand-checked". */
  spec_source?: string;
}

export interface RecallRecord {
  recall_number: string;
  recall_id: number;
  recall_date: string;
  title: string;
  description: string;
  url: string;
  product_names: string[];
  units: string | null;
  hazards: string[];
  remedies: string[];
  remedy_options: string[];
  retailers: string[];
  manufacturers: string[];
  importers: string[];
  images: string[];
  upcs: string[];
  regex_ids: string[];
  is_childrens: boolean;
  corpus: string[];
  spec?: RecallSpec;
}

export interface MatchVerdict {
  verdict: Verdict;
  identifiers_found: string[];
  conflicts: string[];
  reason: string;
}

export interface Listing {
  listing_id: string;
  source: "ebay" | "inventory";
  title: string;
  subtitle: string | null;
  condition: string | null;
  price: string | null;
  link: string | null;
  thumbnail: string | null;
  seller_hash: string | null;
  item_specifics: Record<string, string>;
  query: string | null;
  recall_number: string;
  fetched_at: string;
}

/** GET /api/scan/{recall_number} → listings, each with the model's verdict. */
export interface ScannedListing extends Listing {
  verdict: MatchVerdict;
  /** UI extension: a human confirmed this verdict. */
  human_verified?: boolean;
}

export interface ScanDetail {
  recall_number: string;
  listings: ScannedListing[];
  placeholder?: boolean;
}

export interface ScanByRecall {
  recall_number: string;
  title: string;
  listings: number;
  match: number;
  check: number;
  examples: string[];
  is_childrens?: boolean;
}

export interface ScanSummary {
  recalls_scanned: number;
  searches_spent: number;
  listings_seen: number;
  flagged_match: number;
  flagged_check: number;
  human_verified_match: number;
  childrens_flagged: number;
  by_recall: ScanByRecall[];
  generated_at: string;
  placeholder?: boolean;
  note?: string;
}

export interface DoNotSell {
  item: string;
  recall_number: string;
  recall_title: string;
  why: string;
  remedy: string;
}

export interface CheckLabel {
  item: string;
  recall_number: string;
  look_for: string | null;
  /** UI extension. */
  recall_title?: string;
}

export interface AppliedMemory {
  memory_id: string;
  text: string;
}

export interface RecallCard {
  id: string;
  week_of: string;
  shop_id: string;
  shop_name: string;
  new_recalls: number;
  items_checked: number;
  do_not_sell: DoNotSell[];
  check_label: CheckLabel[];
  applied_memories: AppliedMemory[];
  workflow_id: string;
  model: string;
  generated_at: string;
  placeholder?: boolean;
}

export type StepStatus = "pending" | "scheduled" | "running" | "retrying" | "completed" | "failed";

export interface WorkflowStep {
  name: string;
  status: StepStatus | string;
  attempt: number;
  started_at: string | null;
  ended_at: string | null;
  error?: string | null;
  note?: string | null;
}

export interface CardStatus {
  status: "running" | "completed" | "failed" | string;
  card?: RecallCard;
  steps: WorkflowStep[];
  workflow_id?: string;
  placeholder?: boolean;
}

export interface WorkflowRun {
  workflow_id: string;
  workflow_type?: string;
  shop_id?: string;
  status: string;
  started_at: string | null;
  ended_at: string | null;
  steps: WorkflowStep[];
  retries?: number;
  resumed_after_crash?: boolean;
  workers?: string[];
  history_events?: number;
  card_id?: string;
  placeholder?: boolean;
}

export interface InventoryItem {
  name: string;
  brand?: string;
  model?: string;
  notes?: string;
}

export interface Memory {
  memory_id: string;
  shop_id?: string;
  text: string;
  recall_number?: string | null;
  correct_verdict?: Verdict | null;
  created_at?: string;
  placeholder?: boolean;
}

export interface Correction {
  listing_or_item: string;
  recall_number: string;
  correct_verdict: Verdict;
  note: string;
}

export interface EvalModel {
  name: string;
  role: string;
  acc: number;
  acc_ci: [number, number];
  macro_f1: number;
  risky_caught: string;
  false_alarms: string;
  json_valid: number;
  p50_latency_ms: number;
  cost_per_1k_usd: number;
}

export interface PairedTest {
  a: string;
  b: string;
  gain: number;
  ci: [number, number];
  only_a: number;
  only_b: number;
  p: number;
}

export interface Confusion {
  labels: Verdict[];
  matrix: number[][];
}

export interface EvalResults {
  test_size: number;
  generated_at: string;
  gold: string;
  models: EvalModel[];
  paired: PairedTest[];
  confusion: Record<string, Confusion>;
  training: {
    base_model: string;
    rank: number;
    steps: number;
    epochs: number;
    lr: number;
    loss_curve: [number, number][];
    test_nll: [number, number][];
  };
  examples: { pair_id: string; listing_title: string; recall_title: string; gold: Verdict; base: Verdict; lora: Verdict }[];
  placeholder?: boolean;
  note?: string;
}
