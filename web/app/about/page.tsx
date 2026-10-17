import type { Metadata } from "next";
import { AboutView } from "@/components/views/about";

export const metadata: Metadata = { title: "About & pricing" };

export default function Page() {
  return <AboutView />;
}
