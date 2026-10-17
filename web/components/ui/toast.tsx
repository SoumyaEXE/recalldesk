"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { Notification, NotificationViewport, type NotificationStatus } from "@/components/base/notification/notification";

/** Tiny global toast store rendered through BoardUI's Notification stack. */
interface ToastItem {
  id: number;
  title: ReactNode;
  description?: ReactNode;
  status?: NotificationStatus;
  duration?: number;
}

let items: ToastItem[] = [];
let seq = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function toast(t: Omit<ToastItem, "id">) {
  const id = ++seq;
  items = [...items.slice(-3), { id, duration: 6000, status: "success", ...t }];
  emit();
  return id;
}

function remove(id: number) {
  items = items.filter((x) => x.id !== id);
  emit();
}

const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => {
    listeners.delete(l);
  };
};
const EMPTY: ToastItem[] = [];

export function Toaster() {
  const list = useSyncExternalStore(subscribe, () => items, () => EMPTY);
  return (
    <NotificationViewport position="bottom-end" className="rd-no-print">
      {list.map((t) => (
        <Notification key={t.id} title={t.title} description={t.description} status={t.status} autoDismissDuration={t.duration} introDelay={0} onDismiss={() => remove(t.id)} />
      ))}
    </NotificationViewport>
  );
}
