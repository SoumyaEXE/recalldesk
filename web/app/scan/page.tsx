import type { Metadata } from "next";
import { ScanView } from "@/components/views/scan";

export const metadata: Metadata = { title: "eBay scan" };

export default function Page() {
  return <ScanView />;
}
