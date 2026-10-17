import type { Metadata } from "next";
import { BillingView } from "@/components/views/settings-billing";

export const metadata: Metadata = { title: "Billing" };

export default function Page() {
  return <BillingView />;
}
