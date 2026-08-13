import type { Metadata, ReactNode } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Research Discovery Agent",
  description: "Foundation for the Research Discovery Agent MVP (RDA-001).",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
