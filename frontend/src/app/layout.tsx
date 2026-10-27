import type { Metadata, Viewport } from "next";

import { AppShell } from "@/components/AppShell";
import { ServiceWorkerRegistrar } from "@/components/ServiceWorkerRegistrar";
import { ToastProvider } from "@/components/Toast";
import { CyberHUDControl } from "@/components/CyberHUDControl";

import "./globals.css";

export const metadata: Metadata = {
  title: "Signal Radar — catch what starts trending early",
  description:
    "Signal Radar watches TikTok, YouTube, X, Reddit, Google Trends and more, and surfaces only what just started growing fast. You set the conditions; it runs 24/7.",
  applicationName: "Signal Radar",
  appleWebApp: { capable: true, title: "Signal Radar", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#080a10",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <ServiceWorkerRegistrar />
        <ToastProvider>
          <AppShell>{children}</AppShell>
          <CyberHUDControl />
        </ToastProvider>
      </body>
    </html>
  );
}