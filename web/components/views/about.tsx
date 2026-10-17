import { RiCheckLine, RiCloseLine } from "@remixicon/react";
import { Page, PageHeader, Panel } from "@/components/rd/app-shell";
import { NavButton } from "@/components/rd/nav-button";
import { VerdictGlyph } from "@/components/rd/verdict";

const PIPELINE = [
  { who: "Big model teaches", what: "Qwen3.5-397B-A17B on Tinker turns each CPSC recall into an identification spec (brand, model numbers, sold window, where the label is) and labels training pairs." },
  { who: "Small model reads", what: "A LoRA on Qwen3.5-4B, trained on Tinker, reads one listing or inventory item against one recall and answers match, check or no match, in strict JSON." },
  { who: "Code decides", what: "Identifiers are checked in code, shop memories from Backboard are applied by code, and Temporal runs it every Thursday with retries and crash recovery." },
  { who: "A human grades", what: "The test set is labelled blind by a person. The eBay numbers we publish are the ones a person verified." },
];

const NOT = [
  ["Not legal advice", "RecallDesk helps you find what to look at. Whether you can sell an item is between you, the CPSC and the manufacturer."],
  ["Text only", "We read listing titles and your inventory notes. We can't see the label photo, so CHECK LABEL means a person has to look."],
  ["US CPSC only", "Recalls from cpsc.gov. No Health Canada, NHTSA car seats or FDA products yet."],
  ["Not a seller-reporting tool", "Seller names are hashed. We don't contact, report or rank sellers."],
] as const;

const PLANS = [
  {
    name: "Shop",
    price: "$15",
    per: "/ month per shop",
    blurb: "Kids' consignment shops and eBay stores.",
    features: ["Weekly card every Thursday after CPSC posts", "Unlimited inventory checks", "Re-check your eBay store listings", "Shop memory: corrections stick"],
    cta: "Start with this week's card",
    href: "/",
    featured: true,
  },
  {
    name: "Consignment event",
    price: "$49",
    per: "per event",
    blurb: "Seasonal kids' sales with hundreds of consignors.",
    features: ["Check every consignor's intake list", "One card per drop-off batch", "Printable pull list for volunteers", "Recalls back to 2023 for older gear"],
    cta: "Check an intake list",
    href: "/check",
    featured: false,
  },
];

export function AboutView() {
  return (
    <Page>
      <PageHeader
        eyebrow="About"
        title="Before you list it, check it"
        description="Reselling a recalled product is a federal violation in the US, and recalled baby gear keeps turning up on eBay, Marketplace and Craigslist. CPSC publishes about a dozen recalls every Thursday as long blocks of text, and the model numbers that matter are buried in the description. RecallDesk reads them for you and prints one card."
      />

      <div className="flex flex-col gap-6">
        <section aria-labelledby="who-pays" className="flex flex-col gap-3">
          <h2 id="who-pays" className="rd-notice text-[26px] text-text-primary">
            Who pays
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            {PLANS.map((p) => (
              <div
                key={p.name}
                className={
                  p.featured
                    ? "rd-ruled flex flex-col gap-4 rounded-2xl border-2 border-accent-600 bg-background-primary-default p-5 ps-12 shadow-card"
                    : "flex flex-col gap-4 rounded-2xl border border-border-button-default bg-background-primary-default p-5 shadow-card"
                }
              >
                <div className="flex flex-col gap-1">
                  <p className="rd-eyebrow text-text-tertiary">{p.name}</p>
                  <p className="flex items-baseline gap-1.5">
                    <span className="rd-figure text-[52px] text-text-primary">{p.price}</span>
                    <span className="text-body-2-medium text-text-secondary">{p.per}</span>
                  </p>
                  <p className="text-body-2-regular text-text-secondary">{p.blurb}</p>
                </div>
                <ul className="flex flex-col gap-2">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-body-2-regular text-text-primary">
                      <RiCheckLine className="mt-0.5 size-4 shrink-0 text-ink" aria-hidden />
                      {f}
                    </li>
                  ))}
                </ul>
                <NavButton href={p.href} variant={p.featured ? "primary" : "secondary"} className="mt-auto w-fit">
                  {p.cta}
                </NavButton>
              </div>
            ))}
          </div>
          <p className="text-caption-1-regular text-text-tertiary">
            Why it&apos;s worth it: one recalled bassinet sold is a liability problem and a refund. A volunteer checking 300 intake items by hand against cpsc.gov takes an afternoon.
          </p>
        </section>

        <Panel title="How it works" description="The big model teaches, the small model reads, code decides, a human grades.">
          <ol className="grid gap-4 sm:grid-cols-2">
            {PIPELINE.map((s, i) => (
              <li key={s.who} className="flex gap-3">
                <span className="rd-figure flex size-8 shrink-0 items-center justify-center rounded-lg bg-background-secondary-default text-[18px] text-ink">{i + 1}</span>
                <div className="flex flex-col gap-0.5">
                  <p className="text-body-2-semibold text-text-primary">{s.who}</p>
                  <p className="text-body-2-regular text-text-secondary">{s.what}</p>
                </div>
              </li>
            ))}
          </ol>
        </Panel>

        <div className="grid gap-4 md:grid-cols-2">
          <Panel title="Why open models">
            <ul className="flex flex-col gap-2.5 text-body-2-regular text-text-secondary">
              <li>
                <span className="font-semibold text-text-primary">It runs every week, forever.</span> A 4B model costs cents per thousand checks, so $15 a month covers it with room to spare.
              </li>
              <li>
                <span className="font-semibold text-text-primary">Your inventory stays yours.</span> Open weights can run on a box in the back office. Nothing has to leave the shop.
              </li>
              <li>
                <span className="font-semibold text-text-primary">We can show our work.</span> The eval protocol, test set and numbers live in the repo, so anyone can rerun them.
              </li>
              <li>
                <span className="font-semibold text-text-primary">Small and specific beats big and general here.</span> The Model Lab puts the fine-tuned 4B next to the 397B teacher on accuracy, cost and latency.
              </li>
            </ul>
          </Panel>

          <Panel title="What this is not">
            <ul className="flex flex-col gap-2.5">
              {NOT.map(([k, v]) => (
                <li key={k} className="flex items-start gap-2.5">
                  <RiCloseLine className="mt-0.5 size-4 shrink-0 text-stop-text" aria-hidden />
                  <span className="text-body-2-regular text-text-secondary">
                    <span className="font-semibold text-text-primary">{k}.</span> {v}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        <Panel title="Reading the card">
          <dl className="grid gap-4 sm:grid-cols-3">
            {(
              [
                ["match", "Do not sell", "The listing or item is the recalled product: brand and product line agree, and a recalled identifier shows, or the recall covers every unit."],
                ["check", "Check label", "Same brand and product line, but the label decides it (model number, date code, size). The card tells you exactly where to look."],
                ["no_match", "Clear", "A different product, a model the recall excludes, or only an accessory or empty box. Not shown on the card."],
              ] as const
            ).map(([v, k, d]) => (
              <div key={v} className="flex gap-3">
                <VerdictGlyph verdict={v} className="mt-0.5 size-6" />
                <div>
                  <dt className="rd-notice text-[18px] text-text-primary">{k}</dt>
                  <dd className="text-body-2-regular text-text-secondary">{d}</dd>
                </div>
              </div>
            ))}
          </dl>
        </Panel>

        <p className="text-caption-1-regular text-text-tertiary">
          Recall data: U.S. Consumer Product Safety Commission (saferproducts.gov API). Listings: eBay via SerpApi. Built for the DEV Hacktoberfest Open-Source AI Challenge, Week 2.
        </p>
      </div>
    </Page>
  );
}
