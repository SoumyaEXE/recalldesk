import type { Metadata } from "next";
import { MemoryView } from "@/components/views/memory";

export const metadata: Metadata = { title: "Shop memory" };

export default function Page() {
  return <MemoryView />;
}
