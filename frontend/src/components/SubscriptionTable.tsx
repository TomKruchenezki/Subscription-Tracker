"use client";
import type { Subscription } from "@/types/api";
import { formatMonthly } from "@/lib/format";

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
  // Only divide by 12 when billing_cycle is confirmed ANNUAL — not for UNKNOWN cycles.
  // This prevents ILS₪12.90 with an inferred ANNUAL cycle from showing as ₪1.07/mo.
  const monthly = sub.billing_cycle === "ANNUAL" ? sub.amount / 12 : sub.amount;
  return formatMonthly(monthly, sub.currency);
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
          <th>First charged</th>
          <th>Last charged</th>
        </tr>
      </thead>
      <tbody>
        {subscriptions.map((sub) => (
          <tr key={sub.subscription_id} style={{ opacity: sub.status !== "ACTIVE" && sub.status !== "TRIAL" ? 0.5 : 1 }}>
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
            <td style={{ color: "var(--muted)" }}>
              {sub.first_charge_date
                ? new Date(sub.first_charge_date).toLocaleDateString()
                : "—"}
            </td>
            <td style={{ color: "var(--muted)" }}>
              {sub.last_charge_date
                ? new Date(sub.last_charge_date).toLocaleDateString()
                : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
