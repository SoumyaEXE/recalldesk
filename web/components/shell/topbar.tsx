"use client";

import Link from "next/link";
import { useState } from "react";
import {
  RiArrowDownSLine,
  RiBankCardLine,
  RiInformationLine,
  RiMenuLine,
  RiNotification3Line,
  RiSearchLine,
  RiTeamLine,
} from "@remixicon/react";
import { ThemeToggle } from "@/components/application/theme/theme-toggle";
import { Dropdown, DropdownDivider, DropdownPopover, DropdownTrigger } from "@/components/base/dropdown/dropdown";
import { Kbd } from "@/components/base/kbd/kbd";
import { DataSourceChip } from "@/components/rd/data-source-chip";
import { formatDate, shortTitle } from "@/lib/format";
import { useShop } from "@/lib/shop";
import type { RecallRecord } from "@/lib/types";
import { cx } from "@/utils/cx";
import { setPaletteOpen } from "./command-palette";
import { ShopLogo } from "./sidebar";

function Bell({ week }: { week: RecallRecord[] }) {
  const [open, setOpen] = useState(false);
  const kids = week.filter((r) => r.is_childrens).length;
  return (
    <Dropdown isOpen={open} onOpenChange={setOpen}>
      <DropdownTrigger
        aria-label={week.length ? `Notifications: ${week.length} new recalls this Thursday` : "Notifications"}
        className={cx("relative flex size-9 items-center justify-center rounded-lg border border-line bg-card shadow-card transition-colors hover:border-line-strong", open && "border-line-strong")}
      >
        <RiNotification3Line className="size-[18px] text-foreground-icon-secondary" aria-hidden />
        {week.length > 0 && <span className="absolute top-2 end-2 size-2 rounded-full bg-stop-solid ring-2 ring-card" aria-hidden />}
      </DropdownTrigger>
      <DropdownPopover aria-label="Notifications" placement="bottom end" offset={8} className="w-[360px]" dialogClassName="gap-0">
        <div className="flex items-center justify-between gap-2 px-2 pt-1 pb-2.5">
          <p className="text-body-2-semibold text-text-primary">New this Thursday</p>
          {week[0] && <span className="text-caption-1-regular text-text-tertiary">{formatDate(week[0].recall_date, { weekday: "short", month: "short", day: "numeric" })}</span>}
        </div>
        <p className="mx-2 mb-2 rounded-lg bg-subtle px-2.5 py-2 text-caption-1-regular text-text-secondary">
          CPSC posted <span className="font-semibold text-text-primary">{week.length} recalls</span>
          {kids ? (
            <>
              , <span className="font-semibold text-info-text">{kids} for children</span>
            </>
          ) : null}
          . Your inventory was re-checked against them.
        </p>
        <ul className="rd-scroll flex max-h-[300px] flex-col gap-0.5 overflow-y-auto">
          {week.map((r) => (
            <li key={r.recall_number}>
              <Link
                href={`/recalls?open=${r.recall_number}`}
                onClick={() => setOpen(false)}
                className="flex items-start gap-2.5 rounded-lg px-2 py-2 outline-none hover:bg-hover focus-visible:bg-hover"
              >
                <span className={cx("mt-1.5 size-1.5 shrink-0 rounded-full", r.is_childrens ? "bg-info-solid" : "bg-muted-solid")} aria-hidden />
                <span className="flex min-w-0 flex-col">
                  <span className="truncate text-body-2-medium text-text-primary">{shortTitle(r.title)}</span>
                  <span className="truncate text-caption-1-regular text-text-tertiary">
                    <span className="rd-mono">#{r.recall_number}</span> · {r.spec?.hazard_short ?? r.hazards[0]}
                  </span>
                </span>
              </Link>
            </li>
          ))}
          {!week.length && <li className="px-2 py-6 text-center text-body-2-regular text-text-tertiary">You&apos;re all caught up.</li>}
        </ul>
        <DropdownDivider className="my-2" />
        <Link href="/recalls" onClick={() => setOpen(false)} className="rounded-lg px-2 py-1.5 text-center text-body-2-semibold text-accent-600 outline-none hover:bg-hover focus-visible:bg-hover">
          View all recalls
        </Link>
      </DropdownPopover>
    </Dropdown>
  );
}

function AccountMenu() {
  const shop = useShop();
  const [open, setOpen] = useState(false);
  const items = [
    { href: "/settings/billing", label: "Billing & plan", icon: RiBankCardLine },
    { href: "/settings/team", label: "Team", icon: RiTeamLine },
    { href: "/about", label: "About & pricing", icon: RiInformationLine },
  ];
  return (
    <Dropdown isOpen={open} onOpenChange={setOpen}>
      <DropdownTrigger
        aria-label={`Account: ${shop.name}`}
        className={cx("flex h-10 items-center gap-2.5 rounded-xl border border-line bg-card ps-1.5 pe-2 shadow-card transition-colors hover:border-line-strong", open && "border-line-strong")}
      >
        <ShopLogo shop={shop} size="sm" />
        <span className="hidden min-w-0 flex-col text-start leading-tight sm:flex">
          <span className="max-w-[160px] truncate text-caption-1-semibold text-text-primary">{shop.short}</span>
          <span className="text-caption-2-regular text-text-tertiary">{shop.plan} · $15/mo</span>
        </span>
        <RiArrowDownSLine className={cx("size-4 text-foreground-icon-tertiary transition-transform", open && "rotate-180")} aria-hidden />
      </DropdownTrigger>
      <DropdownPopover aria-label="Account menu" placement="bottom end" offset={8} className="w-[272px]">
        <div className="flex items-center gap-2.5 px-2 pt-1 pb-2">
          <ShopLogo shop={shop} />
          <span className="flex min-w-0 flex-col">
            <span className="truncate text-body-2-semibold text-text-primary">{shop.name}</span>
            <span className="truncate text-caption-1-regular text-text-tertiary">{shop.email}</span>
          </span>
        </div>
        <DropdownDivider />
        {items.map((it) => {
          const I = it.icon;
          return (
            <Link key={it.href} href={it.href} onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-2lg px-2 py-1.5 text-body-2-medium text-text-primary outline-none hover:bg-dropdown-item-hover-background focus-visible:bg-dropdown-item-hover-background">
              <I className="size-4 text-foreground-icon-secondary" aria-hidden />
              {it.label}
            </Link>
          );
        })}
        <DropdownDivider />
        <div className="flex items-center justify-between gap-2 px-2 py-1">
          <span className="text-body-2-medium text-text-primary">Appearance</span>
          <ThemeToggle appearance="segmented" size="small" />
        </div>
      </DropdownPopover>
    </Dropdown>
  );
}

export function Topbar({ week, onMenu }: { week: RecallRecord[]; onMenu: () => void }) {
  return (
    <header className="rd-no-print flex h-16 shrink-0 items-center gap-3 border-b border-line px-4 sm:px-6">
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open navigation"
        className="flex size-9 cursor-pointer items-center justify-center rounded-lg border border-line bg-card shadow-card outline-none hover:border-line-strong focus-visible:ring-2 focus-visible:ring-border-focus-ring lg:hidden"
      >
        <RiMenuLine className="size-[18px] text-foreground-icon-secondary" aria-hidden />
      </button>
      <button
        type="button"
        onClick={() => setPaletteOpen(true)}
        aria-label="Search recalls, model numbers and items"
        className="flex h-10 min-w-0 flex-1 cursor-pointer items-center gap-2.5 rounded-xl border border-line bg-subtle px-3 text-start outline-none transition-colors hover:border-line-strong focus-visible:ring-2 focus-visible:ring-border-focus-ring md:max-w-[460px]"
      >
        <RiSearchLine className="size-[18px] shrink-0 text-foreground-icon-tertiary" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-body-2-regular text-text-placeholder">
          <span className="sm:hidden">Search…</span>
          <span className="hidden sm:inline">Search recalls, model numbers, items…</span>
        </span>
        <Kbd className="hidden rounded-md px-1.5 sm:inline-flex">⌘K</Kbd>
      </button>
      <div className="ms-auto flex items-center gap-2 sm:gap-3">
        <DataSourceChip className="hidden md:inline-flex" />
        <Bell week={week} />
        <AccountMenu />
      </div>
    </header>
  );
}
