import {
  RiArchiveStackLine,
  RiBankCardLine,
  RiBrainLine,
  RiDashboardHorizontalLine,
  RiFileList3Line,
  RiFlaskLine,
  RiInformationLine,
  RiNodeTree,
  RiPlugLine,
  RiSettings3Line,
  RiShieldFlashLine,
  RiShoppingBag3Line,
  RiTeamLine,
} from "@remixicon/react";
import type { ComponentType } from "react";

export type NavIcon = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" | "false" }>;
export interface NavEntry {
  href: string;
  label: string;
  icon: NavIcon;
  keywords?: string;
}

export const PRIMARY_NAV: NavEntry[] = [
  { href: "/", label: "Overview", icon: RiDashboardHorizontalLine, keywords: "home this week dashboard" },
  { href: "/inventory", label: "Inventory", icon: RiArchiveStackLine, keywords: "check items csv paste" },
  { href: "/recalls", label: "Recalls", icon: RiShieldFlashLine, keywords: "cpsc" },
  { href: "/ebay", label: "eBay monitor", icon: RiShoppingBag3Line, keywords: "scan listings serpapi" },
  { href: "/cards", label: "Weekly cards", icon: RiFileList3Line, keywords: "print notice card" },
];

export const SETTINGS_NAV: NavEntry[] = [
  { href: "/settings/services", label: "Connected services", icon: RiPlugLine, keywords: "tinker serpapi backboard temporal sentry health" },
  { href: "/memory", label: "Shop memory", icon: RiBrainLine, keywords: "backboard corrections" },
  { href: "/settings/team", label: "Team", icon: RiTeamLine, keywords: "members" },
  { href: "/settings/billing", label: "Billing", icon: RiBankCardLine, keywords: "payments plan subscription" },
];

export const INSIGHTS_NAV: NavEntry[] = [
  { href: "/lab", label: "Model Lab", icon: RiFlaskLine, keywords: "eval lora tinker accuracy" },
  { href: "/runs", label: "Workflow runs", icon: RiNodeTree, keywords: "temporal" },
  { href: "/about", label: "About & pricing", icon: RiInformationLine, keywords: "pricing what this is not" },
];

export const SETTINGS_ICON = RiSettings3Line;
export const ALL_NAV: NavEntry[] = [...PRIMARY_NAV, ...SETTINGS_NAV, ...INSIGHTS_NAV];

export function isActive(pathname: string, href: string) {
  const p = pathname.replace(/\/$/, "") || "/";
  return href === "/" ? p === "/" : p === href || p.startsWith(`${href}/`);
}
