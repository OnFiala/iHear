import type { Metadata, Viewport } from "next";
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/manrope";
import "./globals.css";
export const metadata: Metadata = {
  title: { default: "iHear — Listening log", template: "%s · iHear" },
  description:
    "Record listening moments for your next visit. An illustrative demo for patients and clinicians.",
  manifest: "/manifest.webmanifest",
  icons: { icon: "/icon.svg", apple: "/app-icon.png" },
  appleWebApp: { capable: true, statusBarStyle: "default", title: "iHear" },
};
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ffffff",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}
