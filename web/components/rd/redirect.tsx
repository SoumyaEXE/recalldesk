"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Client-side redirect for renamed routes (works in the static export too). */
export function Redirect({ to }: { to: string }) {
  const router = useRouter();
  useEffect(() => {
    router.replace(to + window.location.search);
  }, [router, to]);
  return (
    <p className="px-8 py-10 text-body-2-regular text-text-tertiary">
      This page moved. <Link href={to} className="text-accent-600 underline">Continue</Link>
    </p>
  );
}
