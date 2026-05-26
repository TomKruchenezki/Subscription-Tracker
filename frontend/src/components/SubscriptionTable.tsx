"use client";
import type { Subscription } from "@/types/api";

interface Props {
  subscriptions: Subscription[];
}

const CYCLE_LABELS: Record<string, string> = {
  MONTHLY: "Monthly",
  ANNUAL: "Annual",
  WEEKLY: "Weekly",
  UNKNOWN: "—",
};

function monthlyEquivalent(sub: Subscription): string {
  if (sub.amount == null) return "—";
  const monthly = sub.billing_cycle === "ANNUAL" ? sub.amount / 12 : sub.amount;
  return `$${monthly.toFixed(2)}/mo`;
}

export function SubscriptionTable({ subscriptions }: Props) {
  if (subscriptions.length === 0) {
    return (
      <p style={{ color: "var(--muted)" }}>
        No subscriptions found. Run a scan to detect subscriptions from your email source.
      </p>
    );
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Service</th>
          <th>Amount</th>
          <th>Cycle</th>
          <th>Category</th>
          <th>Status</th>
          <th>Source</th>
          <th>Last seen</th>
        </tr>
      </thead>
      <tbody>
        {subscriptions.map((sub) => (
          <tr key={sub.subscription_id} style={{ opacity: sub.status !== "ACTIVE" ? 0.5 : 1 }}>
            <td style={{ fontWeight: 500 }}>{sub.name}</td>
            <td>{monthlyEquivalent(sub)}</td>
            <td>{CYCLE_LABELS[sub.billing_cycle]}</td>
            <td style={{ color: "var(--muted)" }}>{sub.category}</td>
            <td>
              <span className={`badge badge-${sub.status.toLowerCase()}`}>{sub.status}</span>
            </td>
            <td>
              <span className={`badge badge-${sub.source_provider.toLowerCase()}`}>{sub.source_provider}</span>
            </td>
            <td style={{ color: "var(--muted)" }}>{new Date(sub.last_seen).toLocaleDateString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
