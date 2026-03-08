import type { Metadata } from "next";
import { DM_Sans, Instrument_Serif, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import Auth0ProviderWrapper from "./providers/Auth0ProviderWrapper";

const dmSans = DM_Sans({
  variable: "--font-dm-sans",
  subsets: ["latin"],
});

const instrumentSerif = Instrument_Serif({
  variable: "--font-instrument-serif",
  weight: "400",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Clarus — Intelligent Clinical Workflow Automation",
  description:
    "Automate clinical workflows with event-driven triggers. When a clinical event occurs, Clarus contacts patients, books appointments, and coordinates follow-ups automatically.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${dmSans.variable} ${instrumentSerif.variable} ${jetbrainsMono.variable} antialiased`}
        suppressHydrationWarning
      >
        <Auth0ProviderWrapper>{children}</Auth0ProviderWrapper>
      </body>
    </html>
  );
}
