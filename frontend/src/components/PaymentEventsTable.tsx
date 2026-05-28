"use client";
import type { PaymentEvent } from "@/types/api";
import { formatCurrency } from "@/lib/format";

/**
 * PaymentEventsTable — renders the payment_events financial event log.
 *
 * Privacy: displays only safe structured fields. No raw email content
 * (subject, sender address, snippet, body text) is stored in payment_events
 * and therefore cannot appear here.
 *
 * Columns: Date | Type | Merchant | Amount | Recurring | One-time | Linked
 */

const EVENT_TYPE_LABELS: Record<string, string> = {
  subscription_charge: "Subscription charge",
  renewal_charge:      "Renewal",
  one_time_charge:     "One-time",
  refund:              "Refund",
  cancellation:        "Cancellation",
  trial_started:       "Trial started",
  trial_ended:         "Trial ended",
  failed_payment:      "Failed payment",
  price_change:        "Price change",
  unknown_payment:     "Unknown payment",
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  subscription_charge: "var(--green)",
  renewal_charge:      "var(--green)",
  refund:              "var(--yellow)",
  cancellation:        "var(--red)",
  trial_started:       "var(--accent)",
  trial_ended:         "var(--muted)",
  failed_payment:      "var(--red)",
  price_change:        "var(--yellow)",
  one_time_charge:     "var(--text)",
  unknown_payment:     "var(--muted)",
};

interface Props {
  events: PaymentEvent[];
}

export function PaymentEventsTable({ events }: Props) {
  if (events.length === 0) {
    return (
      <p style={{ color: "var(--muted)", padding: "16px 0" }}>
        No payment events recorded. Run a scan to detect financial events from your emails.
      </p>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Type</th>
            <th>Merchant</th>
            <th>Amount</th>
            <th title="Confirmed recurring subscription evidence">Recurring</th>
            <th title="One-time payment evidence">One-time</th>
            <th title="Linked to a subscription record">Linked</th>
            <th title="Detection confidence">Conf.</th>
          </tr>
        </thead>
        <tbody>
          {events.map((ev) => (
            <tr key={ev.event_id}>
              <td style={{ color: "var(--muted)", whiteSpace: "nowrap" }}>
                {ev.event_date.slice(0, 10)}
              </td>
              <td>
                <span style={{ color: EVENT_TYPE_COLORS[ev.event_type] ?? "var(--text)", fontSize: "13px" }}>
                  {EVENT_TYPE_LABELS[ev.event_type] ?? ev.event_type}
                </span>
              </td>
              <td style={{ fontWeight: 500 }}>{ev.merchant_name}</td>
              <td style={{ whiteSpace: "nowrap" }}>
                {ev.amount != null
                  ? formatCurrency(ev.amount, ev.currency)
                  : <span style={{ color: "var(--muted)" }}>—</span>}
              </td>
              <td style={{ textAlign: "center" }}>
                {ev.is_recurring_candidate ? "✓" : <span style={{ color: "var(--muted)" }}>—</span>}
              </td>
              <td style={{ textAlign: "center" }}>
                {ev.is_one_time_candidate ? "✓" : <span style={{ color: "var(--muted)" }}>—</span>}
              </td>
              <td style={{ textAlign: "center" }}>
                {ev.subscription_id
                  ? <span style={{ color: "var(--green)" }}>✓</span>
                  : <span style={{ color: "var(--muted)" }}>—</span>}
              </td>
              <td style={{ color: "var(--muted)", fontSize: "12px" }}>
                {Math.round(ev.confidence_score * 100)}%
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
