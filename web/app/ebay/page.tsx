import type { Metadata } from "next";
import { Suspense } from "react";
import { EbayView } from "@/components/views/ebay";

export const metadata: Metadata = { title: "eBay monitor" };

export default function Page() {
  return (
    <Suspense>
      <EbayView />
    </Suspense>
  );
}
