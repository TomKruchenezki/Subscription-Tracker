import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Subscription Tracker",
  description: "Privacy-first, local-first Gmail subscription tracker",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav style={{ padding: "12px 24px", borderBottom: "1px solid var(--border)", display: "flex", gap: "24px", alignItems: "center" }}>
          <span style={{ fontWeight: 600, color: "var(--text)" }}>Subscription Tracker</span>
          <a href="/">Dashboard</a>
          <a href="/review">Review Queue</a>
          <a href="/accounts">Accounts</a>
        </nav>
        <main style={{ padding: "24px", maxWidth: "1200px", margin: "0 auto" }}>
          {children}
        </main>
      </body>
    </html>
  );
}
