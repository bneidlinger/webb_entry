import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "WebbWatch AI",
  description: "Live JWST data discovery and analysis.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-webb-deep text-webb-star antialiased">{children}</body>
    </html>
  );
}
