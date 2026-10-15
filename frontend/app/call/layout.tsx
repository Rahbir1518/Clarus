import type { Metadata } from "next";

// A call link is a private credential in a URL: keep it out of search indexes
// and out of the Referer header sent to any third party the page loads.
export const metadata: Metadata = {
  title: "Your call",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

export default function CallLayout({ children }: { children: React.ReactNode }) {
  return children;
}
