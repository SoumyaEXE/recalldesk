import type { Metadata } from "next";
import { CardsView } from "@/components/views/cards";

export const metadata: Metadata = { title: "Weekly cards" };

export default function Page() {
  return <CardsView />;
}
