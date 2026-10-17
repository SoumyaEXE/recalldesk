"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { RiAddLine, RiArrowDownSLine, RiCheckLine, RiSearchLine, RiSparkling2Fill } from "@remixicon/react";
import { Dropdown, DropdownDivider, DropdownGroup, DropdownItem, DropdownPopover, DropdownTrigger } from "@/components/base/dropdown/dropdown";
import { Kbd } from "@/components/base/kbd/kbd";
import { ChevronUpDownSmall } from "@/components/foundations/icons/chevrons";
import { SHOPS, type Shop } from "@/lib/api";
import { setShop, useShop } from "@/lib/shop";
import { LogoMark } from "@/components/rd/logo";
import { cx } from "@/utils/cx";
import { setPaletteOpen } from "./command-palette";
import { INSIGHTS_NAV, isActive, PRIMARY_NAV, SETTINGS_ICON, SETTINGS_NAV, type NavEntry } from "./nav";

export function ShopLogo({ shop, size = "md" }: { shop: Shop; size?: "sm" | "md" }) {
  return (
    <span
      className={cx(
        "flex shrink-0 items-center justify-center font-semibold text-white shadow-[inset_0_1px_0_rgb(255_255_255/0.25)]",
        size === "md" ? "size-9 rounded-[10px] text-caption-1-bold" : "size-7 rounded-lg text-caption-2-bold",
        shop.tone === "blue" ? "bg-linear-to-b from-accent-400 to-accent-600" : "bg-linear-to-b from-chart-2 to-chart-2-active",
      )}
      aria-hidden
    >
      {shop.initials}
    </span>
  );
}

/** Workspace / shop switcher (BoardUI sidebar account-menu recipe). */
function ShopSwitcher({ onNavigate }: { onNavigate?: () => void }) {
  const shop = useShop();
  const [open, setOpen] = useState(false);
  return (
    <Dropdown isOpen={open} onOpenChange={setOpen}>
      <DropdownTrigger
        aria-label={`Shop: ${shop.name}. Switch shop`}
        className={cx("flex w-full items-center gap-2.5 rounded-xl p-1.5 text-start transition-colors", open ? "bg-active-nav" : "hover:bg-hover")}
      >
        <ShopLogo shop={shop} />
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-body-2-semibold text-text-primary">{shop.short}</span>
          <span className="truncate text-caption-1-regular text-text-tertiary">{shop.email}</span>
        </span>
        <ChevronUpDownSmall className="size-4 shrink-0 text-foreground-icon-tertiary" />
      </DropdownTrigger>
      <DropdownPopover aria-label="Switch shop" placement="bottom start" className="w-[264px]">
        <DropdownGroup label="Shops">
          {SHOPS.map((s) => (
            <DropdownItem
              key={s.id}
              selected={s.id === shop.id}
              onSelect={() => {
                setShop(s.id);
                setOpen(false);
                onNavigate?.();
              }}
              className="px-2 py-1.5"
            >
              <ShopLogo shop={s} size="sm" />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-body-2-medium text-text-primary">{s.short}</span>
                <span className="truncate text-caption-1-regular text-text-tertiary">{s.kind}</span>
              </span>
              {s.id === shop.id && <RiCheckLine className="size-4 text-accent-600" aria-hidden />}
            </DropdownItem>
          ))}
        </DropdownGroup>
        <DropdownDivider />
        <DropdownItem onSelect={() => setOpen(false)} className="px-2 py-1.5 text-text-tertiary">
          <RiAddLine className="size-4" aria-hidden />
          <span className="text-body-2-medium">Add a shop</span>
          <span className="ms-auto text-caption-1-regular">$15/mo</span>
        </DropdownItem>
      </DropdownPopover>
    </Dropdown>
  );
}

function NavLink({ item, onNavigate, badge, nested = false }: { item: NavEntry; onNavigate?: () => void; badge?: ReactNode; nested?: boolean }) {
  const pathname = usePathname();
  const active = isActive(pathname, item.href);
  const I = item.icon;
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cx(
        "group flex h-9 items-center gap-2.5 rounded-lg px-2.5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-border-focus-ring",
        nested && "ms-[30px] h-8 px-2",
        active ? "bg-active-nav text-text-primary" : "text-text-secondary hover:bg-hover hover:text-text-primary",
      )}
    >
      {!nested && <I className={cx("size-[18px] shrink-0", active ? "text-text-primary" : "text-foreground-icon-secondary group-hover:text-foreground-icon-primary")} aria-hidden />}
      <span className={cx("min-w-0 flex-1 truncate", active ? "text-body-2-semibold" : "text-body-2-medium")}>{item.label}</span>
      {badge}
    </Link>
  );
}

function SettingsGroup({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const within = SETTINGS_NAV.some((n) => isActive(pathname, n.href));
  const [open, setOpen] = useState(true);
  const expanded = open || within;
  const I = SETTINGS_ICON;
  return (
    <div className="flex flex-col gap-0.5">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls="nav-settings"
        onClick={() => setOpen(!expanded)}
        className={cx(
          "group flex h-9 w-full cursor-pointer items-center gap-2.5 rounded-lg px-2.5 text-start outline-none transition-colors focus-visible:ring-2 focus-visible:ring-border-focus-ring",
          within ? "text-text-primary" : "text-text-secondary hover:bg-hover hover:text-text-primary",
        )}
      >
        <I className="size-[18px] shrink-0 text-foreground-icon-secondary group-hover:text-foreground-icon-primary" aria-hidden />
        <span className={cx("flex-1", within ? "text-body-2-semibold" : "text-body-2-medium")}>Settings</span>
        <RiArrowDownSLine className={cx("size-4 text-foreground-icon-tertiary transition-transform duration-200", !expanded && "-rotate-90")} aria-hidden />
      </button>
      <div id="nav-settings" className={cx("grid transition-[grid-template-rows] duration-200 ease-out", expanded ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <ul className="rd-tree relative flex min-h-0 flex-col gap-0.5 overflow-hidden" aria-label="Settings">
          {SETTINGS_NAV.map((n) => (
            <li key={n.href}>
              <NavLink item={n} onNavigate={onNavigate} nested />
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function PromoCard() {
  return (
    <div className="rd-promo relative overflow-hidden rounded-xl p-4 text-white shadow-[0_8px_24px_-10px_rgb(29_78_216/0.6)]">
      <div className="rd-dots pointer-events-none absolute inset-0 opacity-60" aria-hidden />
      <div className="relative flex flex-col gap-1.5">
        <span className="flex size-8 items-center justify-center rounded-lg bg-white/15 ring-1 ring-white/25" aria-hidden>
          <RiSparkling2Fill className="size-4" />
        </span>
        <p className="mt-1 text-body-semibold">Upgrade to Event</p>
        <p className="text-caption-1-regular text-white/80">Check every consignor&apos;s intake list for a seasonal sale. One card per drop-off batch.</p>
        <Link
          href="/settings/billing"
          className="mt-2 inline-flex h-8 items-center justify-center gap-1.5 rounded-lg bg-white text-body-2-semibold text-accent-700 shadow-sm outline-none transition-colors hover:bg-white/90 focus-visible:ring-2 focus-visible:ring-white/70"
        >
          <RiSparkling2Fill className="size-4" aria-hidden />
          Get Event · $49
        </Link>
      </div>
    </div>
  );
}

export function SidebarBody({ onNavigate, newRecalls }: { onNavigate?: () => void; newRecalls?: number }) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex flex-col gap-3 px-3 pt-3">
        <ShopSwitcher onNavigate={onNavigate} />
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="flex h-9 w-full cursor-pointer items-center gap-2 rounded-lg border border-line bg-subtle px-2.5 text-start outline-none transition-colors hover:border-line-strong focus-visible:ring-2 focus-visible:ring-border-focus-ring"
        >
          <RiSearchLine className="size-4 text-foreground-icon-tertiary" aria-hidden />
          <span className="flex-1 text-body-2-regular text-text-placeholder">Search…</span>
          <Kbd className="rounded-md px-1.5">⌘K</Kbd>
        </button>
      </div>
      <nav aria-label="Primary" className="rd-scroll flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto px-3 pt-4 pb-3">
        <ul className="flex flex-col gap-0.5">
          {PRIMARY_NAV.map((n) => (
            <li key={n.href}>
              <NavLink
                item={n}
                onNavigate={onNavigate}
                badge={
                  n.href === "/recalls" && newRecalls ? (
                    <span className="rounded-full bg-stop-surface px-1.5 text-caption-2-semibold text-stop-text ring-1 ring-stop-border ring-inset tabular-nums" aria-label={`${newRecalls} new this week`}>
                      {newRecalls} new
                    </span>
                  ) : undefined
                }
              />
            </li>
          ))}
          <li className="mt-0.5">
            <SettingsGroup onNavigate={onNavigate} />
          </li>
        </ul>
        <div className="border-t border-dashed border-line-strong" aria-hidden />
        <div className="flex flex-col gap-1">
          <p className="px-2.5 pb-1 text-caption-2-semibold tracking-[0.06em] text-text-tertiary uppercase">Insights</p>
          <ul className="flex flex-col gap-0.5">
            {INSIGHTS_NAV.map((n) => (
              <li key={n.href}>
                <NavLink item={n} onNavigate={onNavigate} />
              </li>
            ))}
          </ul>
        </div>
      </nav>
      <div className="flex flex-col gap-3 px-3 pb-3">
        <div className="[@media(max-height:760px)]:hidden">
          <PromoCard />
        </div>
        <Link href="/about" className="flex items-center gap-2 rounded-lg px-1 outline-none focus-visible:ring-2 focus-visible:ring-border-focus-ring">
          <LogoMark className="size-6" />
          <span className="text-caption-1-semibold text-text-primary">RecallDesk</span>
          <span className="truncate text-caption-1-regular text-text-tertiary">Before you list it, check it.</span>
        </Link>
      </div>
    </div>
  );
}
