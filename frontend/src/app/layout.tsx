import type { Metadata, Viewport } from "next";

import { AppShell } from "@/components/AppShell";

import "./globals.css";

export const metadata: Metadata = {
  title: "Signal Radar",
  description:
    "You decide what to watch. Signal Radar watches it 24/7 and notifies you when an early signal appears.",
  applicationName: "Signal Radar",
  appleWebApp: { capable: true, title: "Signal Radar", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#07090f",
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
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}