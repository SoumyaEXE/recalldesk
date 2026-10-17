import type { Metadata, Viewport } from "next";
import { Barlow_Condensed, IBM_Plex_Mono, Public_Sans } from "next/font/google";
import "@/styles/globals.css";
import { AppShell } from "@/components/rd/app-shell";

const sans = Public_Sans({ variable: "--font-public", subsets: ["latin"], display: "swap" });
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
    { media: "(prefers-color-scheme: light)", color: "#fbfaf5" },
    { media: "(prefers-color-scheme: dark)", color: "#161512" },
  ],
};

// Runs before paint: stored theme, else the OS preference.
const themeScript = `(function(){try{var k='boardui:theme',t=localStorage.getItem(k);if(t!=='dark'&&t!=='light'){t=window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';localStorage.setItem(k,t);}document.documentElement.classList.toggle('dark',t==='dark');}catch(e){}})();`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning className={`${sans.variable} ${mono.variable} ${notice.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body className="min-h-full font-sans">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
