"use client";

import { useSyncExternalStore } from "react";
import { DEMO_SHOP_ID, SHOPS, shopById, type Shop } from "./api";

/**
 * The selected shop (workspace switcher). Persisted per browser; `?shop=` in
 * the URL wins so screenshots and shared links are deterministic.
 */
const KEY = "recalldesk:shop";
const EVENT = "recalldesk:shop-change";

function read(): string {
  if (typeof window === "undefined") return DEMO_SHOP_ID;
  try {
    const q = new URLSearchParams(window.location.search).get("shop");
    if (q && SHOPS.some((s) => s.id === q)) return q;
    const v = window.localStorage.getItem(KEY);
    if (v && SHOPS.some((s) => s.id === v)) return v;
  } catch {
    /* storage blocked */
  }
  return DEMO_SHOP_ID;
}

let cached: string | null = null;
function get(): string {
  if (cached === null) cached = read();
  return cached;
}

function subscribe(cb: () => void) {
  const on = () => {
    cached = read();
    cb();
  };
  window.addEventListener(EVENT, on);
  window.addEventListener("storage", on);
  return () => {
    window.removeEventListener(EVENT, on);
    window.removeEventListener("storage", on);
  };
}

export function setShop(id: string) {
  try {
    window.localStorage.setItem(KEY, id);
    const url = new URL(window.location.href);
    if (url.searchParams.has("shop")) {
      url.searchParams.set("shop", id);
      window.history.replaceState(null, "", url.toString());
    }
  } catch {
    /* storage blocked: this page view only */
  }
  cached = id;
  window.dispatchEvent(new Event(EVENT));
}

export function useShop(): Shop {
  const id = useSyncExternalStore(subscribe, get, () => DEMO_SHOP_ID);
  return shopById(id);
}
