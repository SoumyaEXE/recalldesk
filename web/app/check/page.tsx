import type { Metadata } from "next";
import { CheckView } from "@/components/views/check";

export const metadata: Metadata = { title: "Check items" };

export default function Page() {
  return <CheckView />;
}
