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
<<<<<<< HEAD
  title: "Clarus — Clinical Workflow Automation",
  description: "Intelligent clinical workflow automation platform for healthcare providers",
=======
  title: "Clarus — Intelligent Clinical Workflow Automation",
  description:
    "Automate patient follow-up workflows with event-driven triggers. When a lab report arrives, Clarus contacts patients and books appointments automatically.",
>>>>>>> 004aa6977952688d89290588ee109bcf28f9e1ae
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
      >
        <Auth0ProviderWrapper>{children}</Auth0ProviderWrapper>
      </body>
    </html>
  );
}
