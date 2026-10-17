import type { Metadata, Viewport } from "next";
import { Barlow_Condensed, IBM_Plex_Mono, Inter } from "next/font/google";
import "@/styles/globals.css";
import { AppShell } from "@/components/rd/app-shell";

const sans = Inter({ variable: "--font-inter", subsets: ["latin"], display: "swap" });
const mono = IBM_Plex_Mono({ variable: "--font-plex-mono", subsets: ["latin"], weight: ["400", "500", "600"], display: "swap" });
const notice = Barlow_Condensed({ variable: "--font-barlow", subsets: ["latin"], weight: ["500", "600", "700"], display: "swap" });

export const metadata: Metadata = {
  title: {
    default: "RecallDesk · Check it before you list it",
    template: "%s · RecallDesk",
  },
  description:
    "A weekly recall check for kids' consignment shops and eBay resellers. Every Thursday, new CPSC recalls are matched against your inventory and printed on one card for the intake desk.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f3f4f6" },
    { media: "(prefers-color-scheme: dark)", color: "#07090e" },
  ],
};

// Runs before paint: stored theme, else light (light is the primary theme; dark is a toggle in the account menu).
const themeScript = `(function(){try{var t=localStorage.getItem('boardui:theme');document.documentElement.classList.toggle('dark',t==='dark');}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning className={`${sans.variable} ${mono.variable} ${notice.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full bg-canvas font-sans text-text-primary">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
