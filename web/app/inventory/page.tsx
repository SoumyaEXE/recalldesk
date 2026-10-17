import type { Metadata } from "next";
import { Suspense } from "react";
import { InventoryView } from "@/components/views/inventory";

export const metadata: Metadata = { title: "Inventory" };

export default function Page() {
  return (
    <Suspense>
      <InventoryView />
    </Suspense>
  );
}
