"use client";

import { useEffect, useState } from "react";
import { RiExternalLinkLine, RiRefreshLine } from "@remixicon/react";
import { Button } from "@/components/base/buttons/button";
import { Page, PageHeader } from "@/components/rd/app-shell";
import { Card, DemoBadge, Dot, KeyValue, Pill, Skeleton, type Tone } from "@/components/ui/surface";
import { API_BASE, getEval, getHealthInfo, getScan, type Health } from "@/lib/api";
import { num } from "@/lib/format";
import { formatSweep, nextSweep } from "@/lib/schedule";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/utils/cx";

type State = "connected" | "fallback" | "missing" | "unknown";
const STATE: Record<State, { tone: Tone; label: string }> = {
  connected: { tone: "green", label: "Connected" },
  fallback: { tone: "amber", label: "Fallback" },
  missing: { tone: "gray", label: "Not configured" },
  unknown: { tone: "gray", label: "Not checked" },
};

interface Service {
  id: string;
  name: string;
  mark: string;
  markClass: string;
  role: string;
  state: State;
  rows: [string, React.ReactNode][];
  href: string;
}

function ServiceCard({ s }: { s: Service }) {
  const st = STATE[s.state];
  return (
    <Card as="article" aria-label={s.name} className="rd-rise flex flex-col">
      <div className="flex items-start gap-3 px-5 pt-5">
        <span className={cx("flex size-11 shrink-0 items-center justify-center rounded-xl text-body-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.2)]", s.markClass)} aria-hidden>
          {s.mark}
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex items-center justify-between gap-2">
            <h2 className="truncate text-headline-semibold text-text-primary">{s.name}</h2>
            <span className="flex shrink-0 items-center gap-1.5 rounded-full bg-subtle px-2.5 py-1 text-caption-1-semibold whitespace-nowrap text-text-secondary ring-1 ring-line ring-inset">
              <Dot tone={st.tone} />
              {st.label}
            </span>
          </div>
          <p className="text-caption-1-regular text-text-tertiary">{s.role}</p>
        </div>
      </div>
      <dl className="mx-5 mt-3 mb-4 divide-y divide-line">
        {s.rows.map(([k, v]) => (
          <KeyValue key={k} k={k}>
            {v}
          </KeyValue>
        ))}
      </dl>
      <div className="mt-auto flex items-center justify-between border-t border-line bg-subtle px-5 py-2.5">
        <span className="text-caption-1-regular text-text-tertiary">Key in root .env · never logged</span>
        <a href={s.href} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-caption-1-semibold text-accent-600 hover:underline">
          Docs <RiExternalLinkLine className="size-3.5" aria-hidden />
        </a>
      </div>
    </Card>
  );
}

const mono = (v: React.ReactNode) => <code className="rd-mono break-all text-caption-1-regular text-text-primary">{v}</code>;

export function ServicesView() {
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  const [nonce, setNonce] = useState(0);
  const scan = useLoad(getScan, "scan");
  const ev = useLoad(getEval, "eval");
  useEffect(() => {
    let alive = true;
    getHealthInfo().then((h) => alive && setHealth(h));
    return () => {
      alive = false;
    };
  }, [nonce]);

  const h = health ?? undefined;
  const k = (name: string): State => (!h ? "unknown" : h.keys?.[name] ? "connected" : "missing");
  const model = (h?.model ?? {}) as { provider?: string; model?: string; path?: string; model_path?: string };
  const adapter = model.model_path ?? model.path ?? (ev.data?.training as { model_path?: string | null } | undefined)?.model_path ?? null;
  const mem = typeof h?.memory_backend === "string" ? h.memory_backend : undefined;

  const services: Service[] = [
    {
      id: "tinker",
      name: "Tinker",
      mark: "Ti",
      markClass: "bg-linear-to-b from-chart-3 to-chart-3-active",
      role: "Teacher labels, LoRA training and sampling",
      state: !h ? "unknown" : h.keys?.TINKER_API_KEY ? (model.provider === "tinker" ? "connected" : "fallback") : "missing",
      rows: [
        ["Provider", model.provider ? <Pill size="sm" tone={model.provider === "tinker" ? "blue" : "amber"}>{model.provider}</Pill> : "tinker | openai | heuristic"],
        ["Model", mono(model.model ?? "qwen3.5-4b-recalldesk-lora")],
        ["Adapter path", mono(adapter ?? "tinker://… (written after training)")],
        ["Teacher", mono("Qwen/Qwen3.5-397B-A17B")],
      ],
      href: "https://tinker-docs.thinkingmachines.ai/",
    },
    {
      id: "serpapi",
      name: "SerpApi",
      mark: "S",
      markClass: "bg-linear-to-b from-accent-400 to-accent-600",
      role: "eBay engine: live listings for every recall",
      state: k("SERPAPI_API_KEY"),
      rows: [
        ["Engine", mono("engine=ebay · _ipg=50")],
        ["Searches spent", scan.data ? <span className="tabular-nums">{num(scan.data.searches_spent)}</span> : "…"],
        ["Searches left", <span key="l" className="flex items-center gap-2">— <DemoBadge>Not exposed by the API</DemoBadge></span>],
        ["Cache", mono("data/serp/ (sha1 of params)")],
      ],
      href: "https://serpapi.com/ebay-search-api",
    },
    {
      id: "backboard",
      name: "Backboard",
      mark: "B",
      markClass: "bg-linear-to-b from-chart-4 to-chart-4-active",
      role: "Shop memory: one assistant per shop",
      state: !h ? "unknown" : mem === "backboard" ? "connected" : "fallback",
      rows: [
        ["Backend", mem ? mono(mem) : "backboard | local"],
        ["Assistants", "little-loop, flip-garage"],
        ["Retrieval", "Semantic, top-k per item, applied by code"],
      ],
      href: "https://backboard.io",
    },
    {
      id: "temporal",
      name: "Temporal",
      mark: "T",
      markClass: "bg-linear-to-b from-accent-700 to-accent-900",
      role: "WeeklyRecallSweep schedule + InventoryCheckWorkflow",
      state: !h ? "unknown" : h.temporal ? "connected" : "fallback",
      rows: [
        ["Address", mono(h?.temporal_address ?? "localhost:7233")],
        ["Schedule", mono("Thu 14:00 America/New_York")],
        ["Next fire", formatSweep(nextSweep())],
        ["Web UI", <a key="ui" href="http://localhost:8233" target="_blank" rel="noreferrer" className="text-accent-600 hover:underline">localhost:8233</a>],
      ],
      href: "https://docs.temporal.io/",
    },
    {
      id: "sentry",
      name: "Sentry",
      mark: "Se",
      markClass: "bg-linear-to-b from-chart-2 to-chart-2-active",
      role: "Errors and activity traces (optional)",
      state: k("SENTRY_DSN"),
      rows: [
        ["DSN", h?.keys?.SENTRY_DSN ? mono("configured") : "Not set"],
        ["Captures", "API errors, workflow failures"],
      ],
      href: "https://docs.sentry.io/",
    },
    {
      id: "cpsc",
      name: "CPSC Recalls API",
      mark: "C",
      markClass: "bg-linear-to-b from-stop-solid to-stop-text",
      role: "saferproducts.gov REST · no key",
      state: !h ? "unknown" : h.data?.recalls ? "connected" : "fallback",
      rows: [
        ["Endpoint", mono("saferproducts.gov/RestWebServices/Recall")],
        ["Corpus", "A: all since 2026-07-18 · B: children's since 2023"],
        ["Encoding", "UTF-8 decoded explicitly"],
      ],
      href: "https://www.saferproducts.gov/",
    },
  ];

  return (
    <Page>
      <PageHeader
        eyebrow={
          <>
            <Pill size="sm" tone="blue" dot>
              Settings
            </Pill>
            {health === null && <DemoBadge>API offline · showing configuration, not live status</DemoBadge>}
          </>
        }
        title="Connected services"
        description={`Live status from ${API_BASE}/api/health. Keys live only in the root .env; the UI only sees whether each one is set.`}
        actions={
          <Button variant="secondary" leadingIcon={RiRefreshLine} onClick={() => setNonce((n) => n + 1)}>
            Re-check
          </Button>
        }
      />
      {health === undefined ? (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-[260px] rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {services.map((s) => (
            <ServiceCard key={s.id} s={s} />
          ))}
        </div>
      )}
    </Page>
  );
}
