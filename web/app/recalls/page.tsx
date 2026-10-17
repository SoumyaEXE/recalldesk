import type { Metadata } from "next";
import { RecallsView } from "@/components/views/recalls";

export const metadata: Metadata = { title: "Recalls" };

export default function Page() {
  return <RecallsView />;
}
